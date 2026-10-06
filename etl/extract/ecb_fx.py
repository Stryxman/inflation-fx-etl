"""ECB euro foreign exchange reference rates (units of currency per 1 EUR, daily)."""

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

import etl.http
from etl.config import Config
from etl.extract.base import Getter, ParseError, Row

SOURCE: str = "ecb_fx"
TABLE: str = "raw.ecb_fx"
KEY: tuple[str, ...] = ("currency", "date")
LAST: tuple[str, str] | None = ("date", "date")

REQUIRED = ("CURRENCY", "TIME_PERIOD", "OBS_VALUE")


def fetch(cfg: Config, since: date, get: Getter = etl.http.get) -> list[bytes]:
    """Download all currencies in one request, from ``since`` on.

    Args:
        cfg: Pipeline configuration.
        since: First day requested.
        get: HTTP function (injectable for tests).

    Returns:
        A single CSV payload.
    """
    url = cfg.sources[SOURCE]["url"].format(currencies="+".join(c.currency for c in cfg.countries))
    params = {"format": "csvdata", "startPeriod": since.isoformat()}
    return [get(url, params=params)]


def parse(payload: bytes) -> list[Row]:
    """Parse an ECB CSV payload into ``raw.ecb_fx`` rows.

    Args:
        payload: CSV body returned by the ECB data API.

    Returns:
        Rows with ``currency``, ``date``, ``rate`` and ``obs_status``. Empty and ``NaN``
        observations are skipped.

    Raises:
        ParseError: If the payload is not UTF-8 CSV, required columns are missing, or a value
            is malformed.
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
        value = (record["OBS_VALUE"] or "").strip()
        if value == "" or value.lower() == "nan":
            continue
        try:
            rate = Decimal(value)
            day = date.fromisoformat(record["TIME_PERIOD"])
        except (InvalidOperation, ValueError) as exc:
            raise ParseError(f"malformed value in row {record['TIME_PERIOD']!r}: {exc}") from exc
        rows.append(
            {
                "currency": record["CURRENCY"],
                "date": day,
                "rate": rate,
                "obs_status": record.get("OBS_STATUS") or None,
            }
        )
    return rows
