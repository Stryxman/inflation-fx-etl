import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from etl.config import load_config
from etl.extract import oecd_cpi
from etl.extract.base import Extractor, ParseError

FIX = Path(__file__).resolve().parents[1] / "fixtures"
HEADER = (
    "DATAFLOW,REF_AREA,FREQ,METHODOLOGY,MEASURE,UNIT_MEASURE,EXPENDITURE,ADJUSTMENT,"
    "TRANSFORMATION,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
)

assert isinstance(oecd_cpi, Extractor)


def test_contract_constants():
    assert oecd_cpi.SOURCE == "oecd_cpi"
    assert oecd_cpi.TABLE == "raw.oecd_cpi"
    assert oecd_cpi.KEY == ("ref_area", "measure", "period")
    assert oecd_cpi.LAST == ("period", "month")


def test_parse_legacy_fixture_is_yoy():
    rows = oecd_cpi.parse((FIX / "oecd_legacy.csv").read_bytes())
    assert rows
    assert {r["ref_area"] for r in rows} == {"USA", "GBR"}
    assert {r["measure"] for r in rows} == {"yoy"}
    assert all(isinstance(r["value"], Decimal) for r in rows)
    assert set(rows[0]) == {"ref_area", "measure", "period", "value", "obs_status", "dataflow"}
    assert "DF_PRICES_ALL" in str(rows[0]["dataflow"])
    assert all(re.fullmatch(r"\d{4}-\d{2}", str(r["period"])) for r in rows)
    assert all(isinstance(r["period"], str) for r in rows)
    assert {"2025-11", "2025-09"} <= {r["period"] for r in rows if r["ref_area"] == "USA"}
    assert rows[0]["obs_status"] == "A"


def test_parse_c2018_fixture_is_index():
    rows = oecd_cpi.parse((FIX / "oecd_c2018.csv").read_bytes())
    assert {r["ref_area"] for r in rows} == {"TUR", "ZAF"}
    assert {r["measure"] for r in rows} == {"index"}
    assert "DF_PRICES_C2018_ALL" in str(rows[0]["dataflow"])


def test_usa_2025_10_gap_is_not_interpolated():
    rows = oecd_cpi.parse((FIX / "oecd_legacy.csv").read_bytes())
    usa = {r["period"] for r in rows if r["ref_area"] == "USA"}
    assert "2025-10" not in usa
    assert "2025-09" in usa and "2025-11" in usa


@pytest.mark.parametrize("raw", ["", "NaN", "nan"])
def test_empty_and_nan_values_are_skipped(raw):
    body = (
        HEADER + f"DF,USA,M,N,CPI,PA,_T,N,GY,2026-01,{raw},A\n"
        "DF,USA,M,N,CPI,PA,_T,N,GY,2026-03,2.5,A\n"
    )
    rows = oecd_cpi.parse(body.encode())
    assert [r["period"] for r in rows] == ["2026-03"]


def test_bom_payload_is_parsed():
    body = HEADER + "DF,USA,M,N,CPI,PA,_T,N,GY,2026-03,2.5,A\n"
    rows = oecd_cpi.parse(b"\xef\xbb\xbf" + body.encode())
    assert [r["period"] for r in rows] == ["2026-03"]


def test_quarterly_period_raises_parse_error():
    body = HEADER + "DF,USA,Q,N,CPI,PA,_T,N,GY,2026-Q1,2.5,A\n"
    with pytest.raises(ParseError, match="period"):
        oecd_cpi.parse(body.encode())


def test_header_only_gives_no_rows():
    assert oecd_cpi.parse(HEADER.encode()) == []


def test_missing_column_raises_parse_error():
    with pytest.raises(ParseError, match="OBS_VALUE"):
        oecd_cpi.parse(b"DATAFLOW,REF_AREA,TIME_PERIOD\nx,USA,2026-01\n")


def test_html_and_empty_raise_parse_error():
    with pytest.raises(ParseError, match="missing columns"):
        oecd_cpi.parse(b"<html><body>Error</body></html>")
    with pytest.raises(ParseError, match="missing columns"):
        oecd_cpi.parse(b"")


def test_binary_payload_fails_on_decoding():
    with pytest.raises(ParseError, match="not valid UTF-8"):
        oecd_cpi.parse(b"\xff\xfe\x00bad")


def test_unknown_measure_raises_parse_error():
    body = HEADER + "DF,USA,M,N,CPI,XX,_T,N,_Z,2026-01,1.0,A\n"
    with pytest.raises(ParseError, match="measure"):
        oecd_cpi.parse(body.encode())


def test_malformed_value_raises_parse_error():
    body = HEADER + "DF,USA,M,N,CPI,PA,_T,N,GY,2026-01,abc,A\n"
    with pytest.raises(ParseError):
        oecd_cpi.parse(body.encode())


def test_fetch_groups_keys_into_four_sorted_requests():
    cfg = load_config()
    calls: list[tuple[str, dict[str, str], dict[str, str]]] = []
    sleeps: list[float] = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params or {}, headers or {}))
        return b"x"

    out = oecd_cpi.fetch(cfg, date(2026, 9, 21), get=fake_get, sleep=sleeps.append)
    assert {c[1]["startPeriod"] for c in calls} == {"2026-09"}
    assert out == [b"x"] * 4
    assert len(calls) == 4
    legacy = cfg.sources["oecd_cpi"]["url"].format(key="")
    c2018 = cfg.sources["oecd_cpi_c2018"]["url"].format(key="")
    assert [c[0] for c in calls] == [
        legacy + "BRA+GBR+IND+USA.M.N.CPI.IX._T.N._Z",
        legacy + "BRA+GBR+IND+USA.M.N.CPI.PA._T.N.GY",
        c2018 + "CHE+JPN+TUR+ZAF.M.N.CPI.IX._T.N._Z",
        c2018 + "CHE+JPN+TUR+ZAF.M.N.CPI.PA._T.N.GY",
    ]
    for _, params, headers in calls:
        assert params == {"startPeriod": "2026-09", "dimensionAtObservation": "AllDimensions"}
        assert headers == {"Accept": "application/vnd.sdmx.data+csv"}
    assert sleeps == [2, 2, 2]


def test_fetch_ignores_other_sources():
    cfg = load_config()
    urls: list[str] = []

    def fake_get(url, *, params=None, headers=None):
        urls.append(url)
        return b""

    oecd_cpi.fetch(cfg, date(2015, 1, 1), get=fake_get, sleep=lambda _s: None)
    assert not any("ecb.europa.eu" in u for u in urls)


@pytest.mark.parametrize(
    ("since", "expected"), [(date(2015, 1, 1), "2015-01"), (date(2026, 8, 31), "2026-08")]
)
def test_fetch_start_period_follows_since(since, expected):
    cfg = load_config()
    seen: list[str] = []

    def fake_get(url, *, params=None, headers=None):
        seen.append((params or {})["startPeriod"])
        return b""

    oecd_cpi.fetch(cfg, since, get=fake_get, sleep=lambda _s: None)
    assert seen == [expected] * 4
