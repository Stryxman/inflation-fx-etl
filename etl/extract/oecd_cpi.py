"""OECD consumer price indices (monthly) for the territories served by the OECD.

Two dataflows are queried (legacy COICOP 1999 and COICOP 2018) and stored in one table.
"""

import csv
import io
import re
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

import etl.http
from etl.config import Config
from etl.extract.base import Getter, ParseError, Row, month_start
from etl.log import get_logger

log = get_logger(__name__)

SOURCE: str = "oecd_cpi"
TABLE: str = "raw.oecd_cpi"
KEY: tuple[str, ...] = ("ref_area", "measure", "period")
LAST: tuple[str, str] | None = ("period", "month")

DATAFLOW_SOURCES = ("oecd_cpi", "oecd_cpi_c2018")
REQUIRED = (
    "DATAFLOW",
    "REF_AREA",
    "UNIT_MEASURE",
    "TRANSFORMATION",
    "TIME_PERIOD",
    "OBS_VALUE",
)
ACCEPT = "application/vnd.sdmx.data+csv"
PAUSE_SECONDS = 2


def _grouped_keys(cfg: Config) -> list[tuple[str, str, list[str]]]:
    """Group configured keys by (source, key suffix), in a deterministic order."""
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for series in cfg.inflation.values():
        if series.source not in DATAFLOW_SOURCES:
            continue
        for key in (series.key, series.index_key):
            if key:
                area, _, suffix = key.partition(".")
                groups[(series.source, suffix)].add(area)
    return [(src, suffix, sorted(areas)) for (src, suffix), areas in sorted(groups.items())]


def fetch(
    cfg: Config,
    since: date,
    get: Getter = etl.http.get,
    sleep: Callable[[float], None] = time.sleep,
) -> list[bytes]:
    """Download the grouped OECD series, one request per dataflow and key suffix.

    Args:
        cfg: Pipeline configuration.
        since: First day requested (the month containing it is the start period).
        get: HTTP function (injectable for tests).
        sleep: Pause function used between two calls (injectable for tests).

    Returns:
        One SDMX-CSV payload per request.
    """
    payloads: list[bytes] = []
    params = {"startPeriod": month_start(since), "dimensionAtObservation": "AllDimensions"}
    for n, (source, suffix, areas) in enumerate(_grouped_keys(cfg)):
        if n:
            sleep(PAUSE_SECONDS)
        url = cfg.sources[source]["url"].format(key=f"{'+'.join(areas)}.{suffix}")
        log.debug("OECD request %d: %s %s", n + 1, source, suffix)
        payloads.append(get(url, params=params, headers={"Accept": ACCEPT}))
    return payloads


def parse(payload: bytes) -> list[Row]:
    """Parse an OECD SDMX-CSV payload into ``raw.oecd_cpi`` rows.

    Args:
        payload: CSV body returned by the OECD data API.

    Returns:
        Rows with ``ref_area``, ``measure`` (``yoy`` or ``index``), ``period`` (text
        ``YYYY-MM``), ``value``, ``obs_status`` and ``dataflow``. Empty and ``NaN``
        observations are skipped.

    Raises:
        ParseError: If the payload is not UTF-8 CSV, required columns are missing, or a
            value, period or measure is not recognised.
    """
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError(f"payload is not valid UTF-8: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ParseError(f"missing columns: {', '.join(missing)}")
    rows: list[Row] = []
    for record in reader:
        raw = (record["OBS_VALUE"] or "").strip()
        if raw == "" or raw.lower() == "nan":
            continue
        if record["TRANSFORMATION"] == "GY":
            measure = "yoy"
        elif record["UNIT_MEASURE"] == "IX":
            measure = "index"
        else:
            raise ParseError(
                f"cannot infer measure for {record['REF_AREA']!r} {record['TIME_PERIOD']!r}: "
                f"TRANSFORMATION={record['TRANSFORMATION']!r}, "
                f"UNIT_MEASURE={record['UNIT_MEASURE']!r}"
            )
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ParseError(f"malformed value in row {record['TIME_PERIOD']!r}: {exc}") from exc
        period = record["TIME_PERIOD"]
        if not re.fullmatch(r"\d{4}-\d{2}", period):
            raise ParseError(f"unexpected monthly period {period!r} (expected YYYY-MM)")
        rows.append(
            {
                "ref_area": record["REF_AREA"],
                "measure": measure,
                "period": period,
                "value": value,
                "obs_status": record.get("OBS_STATUS") or None,
                "dataflow": record["DATAFLOW"],
            }
        )
    return rows
