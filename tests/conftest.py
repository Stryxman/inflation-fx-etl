import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from etl.config import Config, load_config


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cfg(repo_root: Path) -> Config:
    return load_config(repo_root)


@pytest.fixture
def db(cfg: Config) -> Iterator[psycopg.Connection]:
    """Connection to the test database with the ETL schemas dropped.

    Skips when the database is unreachable, unless CI=true, where the error is real.
    """
    try:
        conn = psycopg.connect(cfg.test_dsn, connect_timeout=3)
    except psycopg.OperationalError:
        if os.environ.get("CI") == "true":
            raise
        pytest.skip("test database is unreachable")
    try:
        conn.execute("DROP SCHEMA IF EXISTS raw, staging, mart, audit CASCADE")
        conn.commit()
        yield conn
    finally:
        conn.rollback()
        conn.close()
