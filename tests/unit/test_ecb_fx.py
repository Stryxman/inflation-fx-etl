from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from etl.extract import ecb_fx
from etl.extract.base import ParseError, month_start, since_for, start_from

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_real_fixture_has_eight_currencies_and_skips_nan():
    rows = ecb_fx.parse((FIX / "ecb_fx.csv").read_bytes())
    assert {r["currency"] for r in rows} == {
        "USD",
        "GBP",
        "JPY",
        "CHF",
        "TRY",
        "BRL",
        "INR",
        "ZAR",
    }
    assert all(isinstance(r["rate"], Decimal) and r["rate"] > 0 for r in rows)
    assert not any(r["date"] == date(2026, 10, 2) for r in rows)  # NaN line skipped
    assert set(rows[0]) == {"currency", "date", "rate", "obs_status"}


def test_header_only_gives_no_rows():
    assert ecb_fx.parse((FIX / "ecb_fx_header_only.csv").read_bytes()) == []


def test_missing_column_raises_parse_error():
    with pytest.raises(ParseError, match="OBS_VALUE"):
        ecb_fx.parse(b"KEY,CURRENCY,TIME_PERIOD\nx,USD,2026-01-02\n")


def test_html_error_page_raises_parse_error():
    with pytest.raises(ParseError):
        ecb_fx.parse(b"<html><body>Service unavailable</body></html>")


def test_empty_payload_raises_parse_error():
    with pytest.raises(ParseError):
        ecb_fx.parse(b"")


def test_start_from_empty_and_incremental():
    assert start_from(None) == date(2015, 1, 1)
    assert start_from(date(2026, 10, 1)) == date(2026, 9, 21)
    assert start_from(date(2015, 1, 5)) == date(2015, 1, 1)


def test_month_start():
    assert month_start(date(2026, 9, 21)) == "2026-09"


def test_contract_constants():
    assert ecb_fx.SOURCE == "ecb_fx"
    assert ecb_fx.TABLE == "raw.ecb_fx"
    assert ecb_fx.KEY == ("currency", "date")
    assert ecb_fx.LAST == ("date", "date")


def test_fetch_builds_one_request_with_all_currencies(cfg):
    calls = []
    out = ecb_fx.fetch(cfg, date(2026, 9, 21), get=lambda url, **kw: calls.append((url, kw)) or b"")
    assert out == [b""]
    assert len(calls) == 1
    url, kw = calls[0]
    assert "D.USD+GBP+JPY+CHF+TRY+BRL+INR+ZAR.EUR.SP00.A" in url
    assert kw["params"] == {"format": "csvdata", "startPeriod": "2026-09-21"}


def test_malformed_value_raises_parse_error():
    payload = b"CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-01-02,abc\n"
    with pytest.raises(ParseError, match="malformed"):
        ecb_fx.parse(payload)


def test_undecodable_payload_raises_parse_error():
    with pytest.raises(ParseError, match="UTF-8"):
        ecb_fx.parse(b"\xff\xfe\x00bad")


def test_since_for_cases():
    assert since_for(None, "date") == date(2015, 1, 1)
    assert since_for(None, "year") == date(2015, 1, 1)
    assert since_for(date(2026, 10, 1), "date") == date(2026, 9, 21)
    assert since_for(date(2026, 9, 1), "month") == date(2026, 8, 22)
    assert since_for(date(2015, 1, 1), "month") == date(2015, 1, 1)
    assert since_for(2024, "year") == date(2024, 1, 1)
    assert since_for(2010, "year") == date(2015, 1, 1)


def test_since_for_unknown_type():
    with pytest.raises(ValueError, match="quarter"):
        since_for(date(2026, 1, 1), "quarter")


def test_since_for_wrong_last_type():
    with pytest.raises(TypeError):
        since_for(2024, "date")
    with pytest.raises(TypeError):
        since_for(date(2024, 1, 1), "year")
