from pathlib import Path

import psycopg
import pytest

from etl.transform.runner import run_layers


@pytest.mark.db
def test_missing_layers_are_skipped(tmp_path: Path, db: psycopg.Connection) -> None:
    assert run_layers(db, tmp_path) == []


@pytest.mark.db
def test_runner_applies_layers_in_order_and_rolls_back_failed_layer(
    tmp_path: Path, db: psycopg.Connection
) -> None:
    (tmp_path / "staging").mkdir()
    (tmp_path / "mart").mkdir()
    db.execute("create schema staging")
    db.commit()
    (tmp_path / "staging" / "10_t.sql").write_text("create table staging.t (a int);")
    (tmp_path / "mart").joinpath("10_ok.sql").write_text("create table staging.m (a int);")
    (tmp_path / "mart").joinpath("20_bad.sql").write_text("select * from does_not_exist;")
    with pytest.raises(psycopg.errors.UndefinedTable, match="does_not_exist"):
        run_layers(db, tmp_path)
    tables = {
        r[0]
        for r in db.execute(
            "select table_name from information_schema.tables where table_schema='staging'"
        ).fetchall()
    }
    assert tables == {"t"}


@pytest.mark.db
def test_runner_returns_applied_files(tmp_path: Path, db: psycopg.Connection) -> None:
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks" / "10_c.sql").write_text("select 1;")
    assert run_layers(db, tmp_path) == ["checks/10_c.sql"]
