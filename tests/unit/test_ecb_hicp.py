from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from etl.extract import ecb_hicp
from etl.extract.base import Extractor, ParseError

FIX = Path(__file__).resolve().parents[1] / "fixtures"
YOY = "M.U2.N.000000.4D0.ANR"
INDEX = "M.U2.N.000000.4D0.INX"


def test_module_satisfies_extractor_contract():
    assert isinstance(ecb_hicp, Extractor)


def test_contract_constants():
    assert ecb_hicp.SOURCE == "ecb_hicp"
    assert ecb_hicp.TABLE == "raw.ecb_hicp"
    assert ecb_hicp.KEY == ("series", "period")
    assert ecb_hicp.LAST == ("period", "month")


def test_parse_yoy_strips_hicp_prefix():
    rows = ecb_hicp.parse((FIX / "ecb_hicp_yoy.csv").read_bytes())
    assert len(rows) == 4
    assert {r["series"] for r in rows} == {YOY}
    assert [r["period"] for r in rows] == ["2026-06", "2026-07", "2026-08", "2026-09"]
    assert rows[0]["value"] == Decimal("2.8")
    assert set(rows[0]) == {"series", "period", "value", "obs_status"}


def test_parse_index_series():
    rows = ecb_hicp.parse((FIX / "ecb_hicp_index.csv").read_bytes())
    assert {r["series"] for r in rows} == {INDEX}
    assert rows[-1]["value"] == Decimal("104.3")


def test_flash_estimate_is_kept_with_status_e():
    rows = ecb_hicp.parse((FIX / "ecb_hicp_yoy.csv").read_bytes())
    assert rows[-1]["period"] == "2026-09"
    assert rows[-1]["obs_status"] == "E"
    assert rows[0]["obs_status"] == "A"


def test_header_only_gives_no_rows():
    header = (FIX / "ecb_hicp_yoy.csv").read_text().splitlines()[0] + "\n"
    assert ecb_hicp.parse(header.encode()) == []


@pytest.mark.parametrize("raw", ["", "NaN", "nan"])
def test_empty_or_nan_value_is_skipped(raw):
    payload = (
        f"KEY,TIME_PERIOD,OBS_VALUE,OBS_STATUS\nHICP.M.X,2026-01,{raw},A\nHICP.M.X,2026-02,1.5,A\n"
    ).encode()
    assert [r["period"] for r in ecb_hicp.parse(payload)] == ["2026-02"]


def test_missing_column_raises_parse_error():
    with pytest.raises(ParseError, match="OBS_VALUE"):
        ecb_hicp.parse(b"KEY,TIME_PERIOD\nHICP.M.X,2026-01\n")


def test_empty_and_html_payloads_raise_parse_error():
    with pytest.raises(ParseError):
        ecb_hicp.parse(b"")
    with pytest.raises(ParseError):
        ecb_hicp.parse(b"<html><body>Service unavailable</body></html>")


def test_malformed_value_raises_parse_error():
    with pytest.raises(ParseError, match="malformed"):
        ecb_hicp.parse(b"KEY,TIME_PERIOD,OBS_VALUE\nHICP.M.X,2026-01,abc\n")


def test_malformed_period_raises_parse_error():
    with pytest.raises(ParseError, match="malformed"):
        ecb_hicp.parse(b"KEY,TIME_PERIOD,OBS_VALUE\nHICP.M.X,2026-01-05,1.5\n")


def test_undecodable_payload_raises_parse_error():
    with pytest.raises(ParseError, match="UTF-8"):
        ecb_hicp.parse(b"\xff\xfe\x00bad")


def test_fetch_makes_two_calls_with_yoy_and_index_keys(cfg):
    calls = []
    out = ecb_hicp.fetch(
        cfg, date(2026, 9, 21), get=lambda url, **kw: calls.append((url, kw)) or b"x"
    )
    assert out == [b"x", b"x"]
    assert len(calls) == 2
    assert calls[0][0].endswith(f"/HICP/{cfg.sources['ecb_hicp']['series']['yoy']}")
    assert calls[1][0].endswith(f"/HICP/{cfg.sources['ecb_hicp']['series']['index']}")
    for url, kw in calls:
        assert "/HICP/" in url
        assert "/ICP/" not in url.replace("/HICP/", "")
        assert kw["params"] == {"format": "csvdata", "startPeriod": "2026-09"}


@pytest.mark.parametrize(
    ("since", "expected"),
    [
        (date(2015, 1, 1), "2015-01"),
        (date(2026, 9, 21), "2026-09"),
        (date(2020, 12, 31), "2020-12"),
    ],
)
def test_fetch_start_period_follows_since(cfg, since, expected):
    calls = []
    ecb_hicp.fetch(cfg, since, get=lambda url, **kw: calls.append(kw) or b"x")
    assert [kw["params"]["startPeriod"] for kw in calls] == [expected, expected]
