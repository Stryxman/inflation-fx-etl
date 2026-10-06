from pathlib import Path

import psycopg
import pytest

from etl.config import Config
from etl.db import apply_schema, connect, schema_files

TABLES = {
    "raw.ecb_fx",
    "raw.ecb_hicp",
    "raw.oecd_cpi",
    "raw.wb_country",
    "raw.wb_inflation",
    "audit.etl_runs",
}


def tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "select table_schema || '.' || table_name from information_schema.tables "
        "where table_schema in ('raw','audit')"
    ).fetchall()
    return {r[0] for r in rows}


def test_schema_files_order(repo_root: Path) -> None:
    rel = [p.relative_to(repo_root).as_posix() for p in schema_files(repo_root)]
    assert rel == [
        "sql/00_schemas.sql",
        "sql/raw/10_ecb_fx.sql",
        "sql/raw/11_ecb_hicp.sql",
        "sql/raw/12_oecd_cpi.sql",
        "sql/raw/13_wb.sql",
        "sql/audit/20_etl_runs.sql",
    ]


def test_schema_files_sorted_within_directory(tmp_path: Path) -> None:
    (tmp_path / "sql" / "raw").mkdir(parents=True)
    (tmp_path / "sql" / "audit").mkdir()
    (tmp_path / "sql" / "00_schemas.sql").write_text("")
    for name in ("sql/raw/12_b.sql", "sql/raw/10_a.sql", "sql/audit/20_c.sql"):
        (tmp_path / name).write_text("")
    (tmp_path / "sql" / "raw" / "notes.txt").write_text("")
    rel = [p.relative_to(tmp_path).as_posix() for p in schema_files(tmp_path)]
    assert rel == [
        "sql/00_schemas.sql",
        "sql/raw/10_a.sql",
        "sql/raw/12_b.sql",
        "sql/audit/20_c.sql",
    ]


@pytest.mark.db
def test_schema_applies_twice(db: psycopg.Connection, repo_root: Path) -> None:
    first = apply_schema(db, repo_root)
    second = apply_schema(db, repo_root)
    assert first == second and first[0] == "sql/00_schemas.sql"
    assert TABLES <= tables(db)


@pytest.mark.db
def test_raw_tables_have_lineage_columns(db: psycopg.Connection, repo_root: Path) -> None:
    apply_schema(db, repo_root)
    for t in TABLES - {"audit.etl_runs"}:
        schema, name = t.split(".")
        cols = {
            r[0]
            for r in db.execute(
                "select column_name from information_schema.columns "
                "where table_schema=%s and table_name=%s",
                (schema, name),
            ).fetchall()
        }
        assert {"_source", "_run_id", "_loaded_at"} <= cols, t


@pytest.mark.db
def test_invalid_period_and_status_are_rejected(db: psycopg.Connection, repo_root: Path) -> None:
    apply_schema(db, repo_root)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "insert into raw.ecb_hicp(series, period, value, obs_status, _source, _run_id) "
            "values ('k', '2026-13x', 1, null, 's', 1)"
        )
    db.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("insert into audit.etl_runs(source, status) values ('x', 'done')")


@pytest.mark.db
def test_connect_disables_autocommit(db: psycopg.Connection, cfg: Config) -> None:
    with connect(cfg.test_dsn) as conn:
        assert conn.autocommit is False


@pytest.mark.db
def test_failed_apply_rolls_back_everything(
    db: psycopg.Connection, repo_root: Path, tmp_path: Path
) -> None:
    (tmp_path / "sql" / "raw").mkdir(parents=True)
    (tmp_path / "sql" / "audit").mkdir()
    (tmp_path / "sql" / "00_schemas.sql").write_text("CREATE SCHEMA raw;")
    (tmp_path / "sql" / "raw" / "10_bad.sql").write_text("CREATE TABLE raw.t (x nonexistent_type);")
    with pytest.raises(psycopg.errors.UndefinedObject):
        apply_schema(db, tmp_path)
    assert tables(db) == set()
    n = db.execute("select count(*) from information_schema.schemata where schema_name='raw'")
    assert n.fetchone() == (0,)


TS = "timestamp with time zone"
LINEAGE = {"_source": ("text", "NO"), "_run_id": ("bigint", "NO"), "_loaded_at": (TS, "NO")}
CONTRACT: dict[str, dict[str, tuple[str, str]]] = {
    "raw.ecb_fx": {
        "currency": ("text", "NO"),
        "date": ("date", "NO"),
        "rate": ("numeric", "NO"),
        "obs_status": ("text", "YES"),
        **LINEAGE,
    },
    "raw.ecb_hicp": {
        "series": ("text", "NO"),
        "period": ("text", "NO"),
        "value": ("numeric", "NO"),
        "obs_status": ("text", "YES"),
        **LINEAGE,
    },
    "raw.oecd_cpi": {
        "ref_area": ("text", "NO"),
        "measure": ("text", "NO"),
        "period": ("text", "NO"),
        "value": ("numeric", "NO"),
        "obs_status": ("text", "YES"),
        "dataflow": ("text", "NO"),
        **LINEAGE,
    },
    "raw.wb_country": {
        "iso3": ("text", "NO"),
        "iso2": ("text", "NO"),
        "name": ("text", "NO"),
        "income_level": ("text", "YES"),
        **LINEAGE,
    },
    "raw.wb_inflation": {
        "iso3": ("text", "NO"),
        "year": ("integer", "NO"),
        "value": ("numeric", "YES"),
        **LINEAGE,
    },
    "audit.etl_runs": {
        "run_id": ("bigint", "NO"),
        "source": ("text", "NO"),
        "started_at": (TS, "NO"),
        "finished_at": (TS, "YES"),
        "status": ("text", "NO"),
        "rows_upserted": ("integer", "YES"),
        "fetch_ms": ("integer", "YES"),
        "parse_ms": ("integer", "YES"),
        "load_ms": ("integer", "YES"),
        "error": ("text", "YES"),
    },
}


@pytest.mark.db
def test_column_contract(db: psycopg.Connection, repo_root: Path) -> None:
    apply_schema(db, repo_root)
    rows = db.execute(
        "select table_schema || '.' || table_name, column_name, data_type, is_nullable "
        "from information_schema.columns where table_schema in ('raw', 'audit')"
    ).fetchall()
    actual: dict[str, dict[str, tuple[str, str]]] = {}
    for table, column, data_type, nullable in rows:
        actual.setdefault(table, {})[column] = (data_type, nullable)
    assert actual == CONTRACT
