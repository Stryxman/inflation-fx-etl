import logging
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest
from psycopg.pq import TransactionStatus

from etl.config import Config
from etl.db import apply_schema
from etl.extract import EXTRACTORS, ecb_fx, oecd_cpi
from etl.http import FetchError
from etl.load import raw_loader
from etl.pipeline import RunResult, run_all, run_source

pytestmark = pytest.mark.db

TABLES = ["raw.ecb_fx", "raw.ecb_hicp", "raw.oecd_cpi", "raw.wb_country", "raw.wb_inflation"]


class FakeGet:
    """Serve the fixtures by URL and record the calls."""

    def __init__(self, repo_root: Path, fail_on: str | None = None) -> None:
        self.dir = repo_root / "tests" / "fixtures"
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        self.calls.append((url, params))
        if self.fail_on and self.fail_on in url:
            raise FetchError(f"GET {url} failed after 3 retries: HTTP 429")
        if "/EXR/" in url:
            name = "ecb_fx.csv"
        elif "HICP/" in url:
            name = "ecb_hicp_yoy.csv" if url.endswith(".ANR") else "ecb_hicp_index.csv"
        elif "COICOP2018" in url:
            name = "oecd_c2018.csv"
        elif "sdmx.oecd.org" in url:
            name = "oecd_legacy.csv"
        elif "/indicator/" in url:
            name = "wb_inflation.json"
        else:
            name = "wb_country.json"
        return (self.dir / name).read_bytes()


@pytest.fixture(autouse=True)
def no_oecd_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oecd_cpi, "PAUSE_SECONDS", 0)


@pytest.fixture
def conn(db: psycopg.Connection, repo_root: Path) -> psycopg.Connection:
    apply_schema(db, repo_root)
    return db


@pytest.fixture
def fake_get(repo_root: Path) -> FakeGet:
    return FakeGet(repo_root)


def counts(conn: psycopg.Connection) -> dict[str, int]:
    return {t: conn.execute(f"select count(*) from {t}").fetchone()[0] for t in TABLES}  # type: ignore[index]


def test_registry_order() -> None:
    assert list(EXTRACTORS) == ["ecb_fx", "ecb_hicp", "oecd_cpi", "wb_country", "wb_inflation"]


def test_run_twice_is_idempotent(conn: psycopg.Connection, cfg: Config, fake_get: FakeGet) -> None:
    first = run_all(conn, cfg, get=fake_get)
    after_first = counts(conn)
    second = run_all(conn, cfg, get=fake_get)
    assert [r.status for r in first + second] == ["success"] * 10
    assert all(n > 0 for n in after_first.values())
    assert counts(conn) == after_first
    ok = conn.execute("select count(*) from audit.etl_runs where status='success'").fetchone()
    assert ok == (10,)
    assert conn.execute("select count(*) from audit.etl_runs").fetchone() == (10,)


def test_failing_source_is_isolated(conn: psycopg.Connection, cfg: Config, repo_root: Path) -> None:
    results = run_all(conn, cfg, get=FakeGet(repo_root, fail_on="sdmx.oecd.org"))
    by_source = {r.source: r for r in results}
    assert by_source["oecd_cpi"].status == "failed"
    assert by_source["oecd_cpi"].error and "HTTP 429" in by_source["oecd_cpi"].error
    assert [r.status for s, r in by_source.items() if s != "oecd_cpi"] == ["success"] * 4
    c = counts(conn)
    assert c["raw.oecd_cpi"] == 0
    assert all(n > 0 for t, n in c.items() if t != "raw.oecd_cpi")
    row = conn.execute(
        "select status, error from audit.etl_runs where source='oecd_cpi'"
    ).fetchone()
    assert row is not None and row[0] == "failed" and "HTTP 429" in row[1]


def test_failure_mid_upsert_leaves_no_partial_rows(
    conn: psycopg.Connection, cfg: Config, fake_get: FakeGet, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = {"currency": "USD", "date": date(2026, 1, 1), "rate": 1, "obs_status": "A"}
    monkeypatch.setattr(
        ecb_fx,
        "parse",
        lambda payload: [
            good,
            {**good, "date": date(2026, 1, 2)},
            {**good, "date": date(2026, 1, 3), "rate": None},
        ],
    )
    result = run_source(conn, cfg, ecb_fx, get=fake_get)
    assert result.status == "failed"
    assert conn.execute("select count(*) from raw.ecb_fx").fetchone() == (0,)
    statuses = conn.execute("select status from audit.etl_runs").fetchall()
    assert statuses == [("failed",)]


def test_success_audit_failure_rolls_back_data_and_commits_failed_audit(
    conn: psycopg.Connection,
    other_conn: psycopg.Connection,
    cfg: Config,
    fake_get: FakeGet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = raw_loader.finish_run

    def finish_run(c: psycopg.Connection, run_id: int, status: str, *args: object, **kw: object):  # type: ignore[no-untyped-def]
        if status == "success":
            raise RuntimeError("audit write failed")
        return real(c, run_id, status, *args, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(raw_loader, "finish_run", finish_run)
    result = run_source(conn, cfg, ecb_fx, get=fake_get)
    assert result.status == "failed"
    # Seen from an independent connection: only committed state counts.
    assert other_conn.execute("select count(*) from raw.ecb_fx").fetchone() == (0,)
    assert other_conn.execute("select status from audit.etl_runs").fetchall() == [("failed",)]
    assert conn.info.transaction_status == TransactionStatus.IDLE


def test_incremental_since_uses_last_loaded_value(
    conn: psycopg.Connection, cfg: Config, fake_get: FakeGet
) -> None:
    run_source(conn, cfg, ecb_fx, get=fake_get)
    assert fake_get.calls[0][1] == {"format": "csvdata", "startPeriod": "2015-01-01"}
    latest = conn.execute("select max(date) from raw.ecb_fx").fetchone()[0]  # type: ignore[index]
    run_source(conn, cfg, ecb_fx, get=fake_get)
    expected = (latest - timedelta(days=10)).isoformat()
    assert fake_get.calls[1][1] == {"format": "csvdata", "startPeriod": expected}


def test_error_message_has_no_credentials(
    conn: psycopg.Connection,
    cfg: Config,
    fake_get: FakeGet,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def boom(payload: bytes) -> list[dict[str, object]]:
        raise RuntimeError(f"cannot connect to {cfg.dsn} (host=db password=etl_local_only)")

    monkeypatch.setattr(ecb_fx, "parse", boom)
    caplog.set_level(logging.DEBUG, logger="etl")
    result = run_source(conn, cfg, ecb_fx, get=fake_get)
    stored = conn.execute("select error from audit.etl_runs").fetchone()[0]  # type: ignore[index]
    assert result.error is not None
    assert "cannot connect to" in stored
    assert "etl_local_only" not in stored
    assert "etl_local_only" not in result.error
    assert "etl_local_only" not in caplog.text


def test_error_message_is_truncated(
    conn: psycopg.Connection, cfg: Config, fake_get: FakeGet, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(payload: bytes) -> list[dict[str, object]]:
        raise RuntimeError("x" * 2000)

    monkeypatch.setattr(ecb_fx, "parse", boom)
    run_source(conn, cfg, ecb_fx, get=fake_get)
    stored = conn.execute("select error from audit.etl_runs").fetchone()[0]  # type: ignore[index]
    assert len(stored) == 500


def test_timings_are_recorded(conn: psycopg.Connection, cfg: Config, fake_get: FakeGet) -> None:
    results = run_all(conn, cfg, get=fake_get)
    for r in results:
        assert set(r.timings) == {"fetch_ms", "parse_ms", "load_ms"}
        assert all(v >= 0 for v in r.timings.values())
    rows = conn.execute("select fetch_ms, parse_ms, load_ms, finished_at from audit.etl_runs")
    fetched = rows.fetchall()
    assert len(fetched) == 5
    assert all(None not in row and min(row[:3]) >= 0 for row in fetched)


def test_logs_per_source(
    conn: psycopg.Connection, cfg: Config, fake_get: FakeGet, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="etl")
    run_all(conn, cfg, get=fake_get)
    for name in EXTRACTORS:
        assert f"{name}: start since=2015-01-01" in caplog.text
        assert f"{name}: fetched " in caplog.text
        assert f"{name}: upserted " in caplog.text
    assert "etl_local_only" not in caplog.text


def test_run_all_subset_and_unknown_name(
    conn: psycopg.Connection, cfg: Config, fake_get: FakeGet
) -> None:
    results = run_all(conn, cfg, names=["ecb_hicp"], get=fake_get)
    assert [r.source for r in results] == ["ecb_hicp"]
    with pytest.raises(ValueError, match=r"unknown source 'nope'"):
        run_all(conn, cfg, names=["nope"], get=fake_get)


def test_upsert_updates_existing_rows(conn: psycopg.Connection) -> None:
    run_id = raw_loader.start_run(conn, "ecb_fx")
    row = {"currency": "USD", "date": date(2026, 1, 1), "rate": 1, "obs_status": "A"}
    assert raw_loader.upsert(conn, "raw.ecb_fx", [row], ("currency", "date"), run_id, "ecb_fx") == 1
    row2 = {**row, "rate": 2}
    raw_loader.upsert(conn, "raw.ecb_fx", [row2], ("currency", "date"), run_id, "ecb_fx")
    conn.commit()
    assert conn.execute("select count(*), max(rate) from raw.ecb_fx").fetchone() == (1, 2)
    assert raw_loader.upsert(conn, "raw.ecb_fx", [], ("currency", "date"), run_id, "ecb_fx") == 0


def test_start_run_is_visible_from_another_connection(
    conn: psycopg.Connection, cfg: Config
) -> None:
    run_id = raw_loader.start_run(conn, "ecb_fx")
    with psycopg.connect(cfg.test_dsn) as other:
        row = other.execute("select status from audit.etl_runs where run_id=%s", (run_id,))
        assert row.fetchone() == ("running",)


@pytest.mark.parametrize(
    ("table", "column", "values", "expected"),
    [
        ("raw.ecb_fx", "date", [date(2026, 1, 5), date(2026, 3, 9)], date(2026, 3, 9)),
        ("raw.ecb_hicp", "period", ["2026-02", "2026-07"], date(2026, 7, 1)),
        ("raw.wb_inflation", "year", [2020, 2023], 2023),
    ],
)
def test_last_value(
    conn: psycopg.Connection, table: str, column: str, values: list[object], expected: object
) -> None:
    assert raw_loader.last_value(conn, table, column) is None
    run_id = raw_loader.start_run(conn, "x")
    for i, v in enumerate(values):
        if table == "raw.ecb_fx":
            row = {"currency": "USD", "date": v, "rate": 1, "obs_status": None}
        elif table == "raw.ecb_hicp":
            row = {"series": "s", "period": v, "value": 1, "obs_status": None}
        else:
            row = {"iso3": "USA", "year": v, "value": None}
        key = {"raw.ecb_fx": ("currency", "date"), "raw.ecb_hicp": ("series", "period")}.get(
            table, ("iso3", "year")
        )
        raw_loader.upsert(conn, table, [row], key, run_id, "x")
        assert i < 2
    conn.commit()
    assert raw_loader.last_value(conn, table, column) == expected


def test_finish_run_rejects_nothing_but_truncates_and_cleans(conn: psycopg.Connection) -> None:
    run_id = raw_loader.start_run(conn, "ecb_fx")
    raw_loader.finish_run(
        conn, run_id, "failed", 0, error="postgresql://u:secretpw@h/db " + "y" * 600
    )
    conn.commit()
    stored = conn.execute("select error from audit.etl_runs").fetchone()[0]  # type: ignore[index]
    assert "secretpw" not in stored and len(stored) == 500


def test_run_result_is_a_value_object() -> None:
    r = RunResult("s", "success", 1, None, {"fetch_ms": 1, "parse_ms": 2, "load_ms": 3})
    assert r.source == "s" and r.rows == 1


@pytest.mark.parametrize(
    ("raw", "forbidden", "expected"),
    [
        ("connect postgresql://u:s3cret@h/db failed", "s3cret", "connect postgresql://h/db failed"),
        ("postgresql://u:pa/ss@h/db", "pa/ss", "postgresql://h/db"),
        ("host=db password=s3cret user=u", "s3cret", "host=db password=*** user=u"),
        ("password='s3 cret' user=u", "cret", "password=*** user=u"),
        ('password="s3 cret" x', "cret", "password=*** x"),
        ('{"user": "u", "password": "s3\\"cret"}', "cret", '{"user": "u", "password": "***"}'),
        ("line1\nline2 password=s3cret\nline3", "s3cret", "line1\nline2 password=***\nline3"),
        ("bad http://[::1 x s", None, "bad <unparseable> x s"),
        ("x\npostgresql://u:pw@h/db", "pw", "x\npostgresql://h/db"),
        ("", None, ""),
        ("\n\t\n", None, "\n\t\n"),
    ],
)
def test_clean_error_hostile_inputs(raw: str, forbidden: str | None, expected: str) -> None:
    cleaned = raw_loader.clean_error(raw)
    assert cleaned == expected
    if forbidden:
        assert forbidden not in cleaned
