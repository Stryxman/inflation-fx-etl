"""ECB euro-area HICP inflation (annual rate of change and index, monthly)."""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import etl.http
from etl.config import Config
from etl.extract.base import Getter, ParseError, Row, month_start

SOURCE: str = "ecb_hicp"
TABLE: str = "raw.ecb_hicp"
KEY: tuple[str, ...] = ("series", "period")
LAST: tuple[str, str] | None = ("period", "month")

REQUIRED = ("KEY", "TIME_PERIOD", "OBS_VALUE")
_PERIOD = re.compile(r"^\d{4}-\d{2}$")
_PREFIX = "HICP."


def fetch(cfg: Config, since: date, get: Getter = etl.http.get) -> list[bytes]:
    """Download the annual-rate and index series, one request each.

    Args:
        cfg: Pipeline configuration.
        since: Date whose month is the first period requested.
        get: HTTP function (injectable for tests).

    Returns:
        Two CSV payloads: the annual rate (``series.yoy``) then the index (``series.index``).
    """
    block = cfg.sources[SOURCE]
    params = {"format": "csvdata", "startPeriod": month_start(since)}
    return [
        get(block["url"].format(key=block["series"][name]), params=params)
        for name in ("yoy", "index")
    ]


def parse(payload: bytes) -> list[Row]:
    """Parse an ECB HICP CSV payload into ``raw.ecb_hicp`` rows.

    Args:
        payload: CSV body returned by the ECB data API.

    Returns:
        Rows with ``series`` (key without the ``HICP.`` prefix), ``period`` (``YYYY-MM``),
        ``value`` and ``obs_status``. Flash estimates (``E``) are kept as is; empty and
        ``NaN`` observations are skipped.

    Raises:
        ParseError: If the payload is not UTF-8 CSV, required columns are missing, or a value
            or period is malformed.
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
        raw_value = (record["OBS_VALUE"] or "").strip()
        if raw_value == "" or raw_value.lower() == "nan":
            continue
        period = record["TIME_PERIOD"]
        if not _PERIOD.match(period):
            raise ParseError(f"malformed period {period!r}: expected YYYY-MM")
        try:
            value = Decimal(raw_value)
        except InvalidOperation as exc:
            raise ParseError(f"malformed value in row {period!r}: {exc}") from exc
        rows.append(
            {
                "series": record["KEY"].removeprefix(_PREFIX),
                "period": period,
                "value": value,
                "obs_status": record.get("OBS_STATUS") or None,
            }
        )
    return rows
