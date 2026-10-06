import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from etl.config import load_config
from etl.extract import worldbank
from etl.extract.base import Extractor, ParseError

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def test_sub_sources_follow_the_contract():
    assert isinstance(worldbank.COUNTRY, Extractor)
    assert isinstance(worldbank.INFLATION, Extractor)
    assert worldbank.COUNTRY.SOURCE == "wb_country"
    assert worldbank.COUNTRY.TABLE == "raw.wb_country"
    assert worldbank.COUNTRY.KEY == ("iso3",)
    assert worldbank.COUNTRY.LAST is None
    assert worldbank.INFLATION.SOURCE == "wb_inflation"
    assert worldbank.INFLATION.TABLE == "raw.wb_inflation"
    assert worldbank.INFLATION.KEY == ("iso3", "year")
    assert worldbank.INFLATION.LAST == ("year", "year")


def test_parse_country_fixture():
    rows = worldbank.COUNTRY.parse((FIX / "wb_country.json").read_bytes())
    by_iso3 = {r["iso3"]: r for r in rows}
    assert set(by_iso3) == {"USA", "TUR"}
    assert by_iso3["USA"] == {
        "iso3": "USA",
        "iso2": "US",
        "name": "United States",
        "income_level": "High income",
    }
    assert by_iso3["TUR"]["income_level"] == "Upper middle income"


def test_parse_inflation_fixture_keeps_null_and_int_year():
    rows = worldbank.INFLATION.parse((FIX / "wb_inflation.json").read_bytes())
    assert len(rows) == 6
    assert all(isinstance(r["year"], int) for r in rows)
    assert set(rows[0]) == {"iso3", "year", "value"}
    by_key = {(r["iso3"], r["year"]): r["value"] for r in rows}
    assert by_key[("USA", 2025)] is None
    assert isinstance(by_key[("TUR", 2025)], Decimal)
    assert by_key[("TUR", 2025)] == Decimal("34.8811629820306")


@pytest.mark.parametrize("tail", ["", ", null"])
def test_error_message_raises_parse_error_with_api_message(tail):
    payload = (
        '[{"message":[{"id":"120","key":"Invalid value","value":"The provided '
        'parameter value is not valid"}]}' + tail + "]"
    ).encode()
    for sub in (worldbank.COUNTRY, worldbank.INFLATION):
        with pytest.raises(ParseError, match="World Bank API error.*Invalid value"):
            sub.parse(payload)


@pytest.mark.parametrize("raw_value", ['"NaN"', "NaN", '"nan"'])
def test_nan_value_row_is_skipped(raw_value):
    payload = (
        '[{}, [{"countryiso3code":"USA","date":"2024","value":' + raw_value + "},"
        '{"countryiso3code":"USA","date":"2023","value":2.5}]]'
    ).encode()
    rows = worldbank.INFLATION.parse(payload)
    assert rows == [{"iso3": "USA", "year": 2023, "value": Decimal("2.5")}]


def test_null_rows_gives_empty_list():
    payload = b'[{"page":0,"pages":0,"per_page":"50","total":0},null]'
    assert worldbank.INFLATION.parse(payload) == []
    assert worldbank.COUNTRY.parse(payload) == []


@pytest.mark.parametrize(
    "payload",
    [b"", b"<html>down</html>", b"\xff\xfe", b'{"a": 1}', b"[1]", b'[{}, {"a": 1}]'],
)
def test_bad_payload_raises_parse_error(payload):
    with pytest.raises(ParseError):
        worldbank.INFLATION.parse(payload)
    with pytest.raises(ParseError):
        worldbank.COUNTRY.parse(payload)


def test_malformed_values_raise_parse_error():
    bad_year = json.dumps([{}, [{"countryiso3code": "USA", "date": "abc", "value": 1.0}]])
    with pytest.raises(ParseError):
        worldbank.INFLATION.parse(bad_year.encode())
    bad_value = json.dumps([{}, [{"countryiso3code": "USA", "date": "2024", "value": "x"}]])
    with pytest.raises(ParseError):
        worldbank.INFLATION.parse(bad_value.encode())


class FakeGet:
    def __init__(self):
        self.calls = []

    def __call__(self, url, *, params=None, headers=None):
        self.calls.append((url, params))
        return b"[{}, []]"


def test_country_fetch_url_has_eight_iso3_codes():
    cfg = load_config()
    get = FakeGet()
    payloads = worldbank.COUNTRY.fetch(cfg, date(2015, 1, 1), get)
    assert len(payloads) == 1
    (url, params) = get.calls[0]
    codes = ";".join(c.iso3 for c in cfg.countries)
    assert len(cfg.countries) == 8
    assert url == f"https://api.worldbank.org/v2/country/{codes}"
    assert params == {"format": "json", "per_page": "100"}


def test_inflation_fetch_requests_since_year_to_current_year():
    cfg = load_config()
    get = FakeGet()
    worldbank.INFLATION.fetch(cfg, date(2025, 1, 1), get)
    (url, params) = get.calls[0]
    codes = ";".join(c.iso3 for c in cfg.countries)
    assert url == f"https://api.worldbank.org/v2/country/{codes}/indicator/FP.CPI.TOTL.ZG"
    assert params == {
        "format": "json",
        "per_page": "1000",
        "date": f"2025:{date.today().year}",
    }
