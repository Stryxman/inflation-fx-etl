"""World Bank country metadata and annual inflation.

The module feeds two tables, so it exposes two sub-sources that follow the extractor
contract: ``COUNTRY`` (full reload, income level) and ``INFLATION`` (annual CPI inflation,
incremental by year; a dormant fallback while monthly series cover every territory).
"""

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

import etl.http
from etl.config import Config
from etl.extract.base import Getter, ParseError, Row

COUNTRY_SOURCE = "wb_country"
INFLATION_SOURCE = "wb_inflation"
DEFAULT_INDICATOR = "FP.CPI.TOTL.ZG"


def _base(cfg: Config) -> str:
    codes = ";".join(c.iso3 for c in cfg.countries)
    return f"{cfg.sources['worldbank']['url']}/country/{codes}"


def _fetch_country(cfg: Config, since: date, get: Getter = etl.http.get) -> list[bytes]:
    """Download the metadata of all tracked countries in one request (``since`` is unused)."""
    return [get(_base(cfg), params={"format": "json", "per_page": "100"})]


def _fetch_inflation(cfg: Config, since: date, get: Getter = etl.http.get) -> list[bytes]:
    """Download annual inflation from ``since.year`` to the current year in one request."""
    indicator = cfg.sources["worldbank"].get("indicator", DEFAULT_INDICATOR)
    params = {
        "format": "json",
        "per_page": "1000",
        "date": f"{since.year}:{date.today().year}",
    }
    return [get(f"{_base(cfg)}/indicator/{indicator}", params=params)]


def _records(payload: bytes) -> list[dict[str, Any]]:
    """Decode a World Bank ``[meta, rows]`` response and return its rows.

    Raises:
        ParseError: If the payload is not UTF-8 JSON in the expected shape or carries a
            World Bank error message.
    """
    try:
        data = json.loads(payload.decode("utf-8-sig"), parse_float=Decimal)
    except UnicodeDecodeError as exc:
        raise ParseError(f"payload is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ParseError(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ParseError("unexpected World Bank response: expected a [meta, rows] list")
    meta = data[0]
    if "message" in meta:
        raise ParseError(f"World Bank API error: {meta['message']}")
    if len(data) < 2:
        raise ParseError("unexpected World Bank response: missing rows element")
    rows = data[1]
    if rows is None:
        return []
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ParseError("unexpected World Bank response: rows is not a list of objects")
    return rows


def _parse_country(payload: bytes) -> list[Row]:
    """Parse a country response into ``raw.wb_country`` rows.

    Returns:
        Rows with ``iso3``, ``iso2``, ``name`` and ``income_level``.

    Raises:
        ParseError: If the payload is not the expected format or a field is missing.
    """
    rows: list[Row] = []
    for rec in _records(payload):
        try:
            rows.append(
                {
                    "iso3": rec["id"],
                    "iso2": rec["iso2Code"],
                    "name": rec["name"],
                    "income_level": (rec.get("incomeLevel") or {}).get("value") or None,
                }
            )
        except KeyError as exc:
            raise ParseError(f"country record missing field {exc}") from exc
    return rows


def _parse_inflation(payload: bytes) -> list[Row]:
    """Parse an indicator response into ``raw.wb_inflation`` rows.

    Returns:
        Rows with ``iso3``, ``year`` (int) and ``value`` (``Decimal``, or ``None`` when the
        World Bank has no observation: the row is kept, nothing is interpolated). Rows whose
        value is ``NaN`` are skipped.

    Raises:
        ParseError: If the payload is not the expected format or a field is malformed.
    """
    rows: list[Row] = []
    for rec in _records(payload):
        try:
            iso3 = rec["countryiso3code"]
            year = int(rec["date"])
        except KeyError as exc:
            raise ParseError(f"inflation record missing field {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ParseError(f"malformed year {rec.get('date')!r}: {exc}") from exc
        raw = rec.get("value")
        try:
            value = None if raw is None else Decimal(str(raw))
        except InvalidOperation as exc:
            raise ParseError(f"malformed value {raw!r} for {iso3} {year}") from exc
        if value is not None and value.is_nan():
            continue  # NaN is not an observation: no row, nothing interpolated
        rows.append({"iso3": iso3, "year": year, "value": value})
    return rows


COUNTRY = SimpleNamespace(
    SOURCE=COUNTRY_SOURCE,
    TABLE="raw.wb_country",
    KEY=("iso3",),
    LAST=None,
    fetch=_fetch_country,
    parse=_parse_country,
)

INFLATION = SimpleNamespace(
    SOURCE=INFLATION_SOURCE,
    TABLE="raw.wb_inflation",
    KEY=("iso3", "year"),
    LAST=("year", "year"),
    fetch=_fetch_inflation,
    parse=_parse_inflation,
)
