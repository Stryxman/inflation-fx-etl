"""Idempotent loading of raw rows and the run journal ``audit.etl_runs``."""

import re
from datetime import date
from typing import Any

import psycopg
from psycopg import sql

from etl.extract.base import Row
from etl.log import redact

MAX_ERROR_CHARS = 500
TIMING_KEYS = ("fetch_ms", "parse_ms", "load_ms")
_PASSWORD_PAIR = re.compile(r"""(?i)(password\s*=\s*)('[^']*'|"[^"]*"|\S+)""")
_PASSWORD_JSON = re.compile(r'(?i)("password"\s*:\s*)"(?:[^"\\]|\\.)*"')
_USERINFO = re.compile(r"(\w+://)[^\s@]*@")
_TOKEN = re.compile(r"\S+")
_PERIOD = re.compile(r"^(\d{4})-(\d{2})$")


def _safe_redact(token: str) -> str:
    try:
        return redact(token)
    except ValueError:
        return "<unparseable>"


def clean_error(message: str) -> str:
    """Make a message safe to store or log: no credentials, at most 500 characters.

    Never raises. Removes ``user:password@`` from URLs (a ``/`` or ``@`` inside the password
    is covered, a space is not), ``password=value`` pairs (bare, single- or double-quoted)
    and JSON ``"password": "value"`` members. Tokens that cannot be parsed as a URL are
    replaced by ``<unparseable>``; line breaks are kept.

    Limits: other secrets (API keys, tokens in query strings, passwords in free text) are
    not recognised, and a password containing a space outside quotes is only masked up
    to its first space.

    Args:
        message: Raw error text, possibly holding a DSN or password pairs.

    Returns:
        The cleaned message, truncated to 500 characters.
    """
    text = _PASSWORD_PAIR.sub(r"\1***", message)
    text = _PASSWORD_JSON.sub(r'\1"***"', text)
    text = _TOKEN.sub(lambda m: _safe_redact(m.group(0)), text)
    text = _USERINFO.sub(r"\1", text)
    return text[:MAX_ERROR_CHARS]


def _table(name: str) -> sql.Identifier:
    return sql.Identifier(*name.split("."))


def start_run(conn: psycopg.Connection, source: str) -> int:
    """Insert a ``running`` journal row and commit it, so it survives a failed load.

    Args:
        conn: Open connection.
        source: Source name.

    Returns:
        The new ``run_id``.
    """
    row = conn.execute(
        "INSERT INTO audit.etl_runs (source, status) VALUES (%s, 'running') RETURNING run_id",
        (source,),
    ).fetchone()
    conn.commit()
    assert row is not None
    run_id: int = row[0]
    return run_id


def upsert(
    conn: psycopg.Connection,
    table: str,
    rows: list[Row],
    key: tuple[str, ...],
    run_id: int,
    source: str,
) -> int:
    """Insert rows, updating those whose key already exists. Does not commit.

    Args:
        conn: Open connection.
        table: Target table as ``schema.table``.
        rows: Rows holding the business columns (the same columns in every row).
        key: Primary-key columns.
        run_id: Journal row of the current run (``_run_id``).
        source: Source name (``_source``).

    Returns:
        The number of rows written.
    """
    if not rows:
        return 0
    columns = list(rows[0])
    updates = [c for c in columns if c not in key]
    query = sql.SQL(
        "INSERT INTO {table} ({cols}, _source, _run_id) VALUES ({vals}, %s, %s) "
        "ON CONFLICT ({keys}) DO UPDATE SET {sets}{sep}_source = EXCLUDED._source, "
        "_run_id = EXCLUDED._run_id, _loaded_at = now()"
    ).format(
        table=_table(table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        vals=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        keys=sql.SQL(", ").join(sql.Identifier(c) for c in key),
        sets=sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in updates
        ),
        sep=sql.SQL(", ") if updates else sql.SQL(""),
    )
    params = [[row[c] for c in columns] + [source, run_id] for row in rows]
    with conn.cursor() as cur:
        cur.executemany(query, params)
    return len(rows)


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    rows: int,
    error: str | None = None,
    timings: dict[str, int] | None = None,
) -> None:
    """Close a journal row. Does not commit, so it can share the load transaction.

    Args:
        conn: Open connection.
        run_id: Journal row to close.
        status: ``success`` or ``failed``.
        rows: Number of rows upserted.
        error: Error text; credentials are removed and it is cut to 500 characters.
        timings: Durations in milliseconds under ``fetch_ms``, ``parse_ms``, ``load_ms``.
    """
    times: dict[str, Any] = {k: (timings or {}).get(k) for k in TIMING_KEYS}
    conn.execute(
        "UPDATE audit.etl_runs SET finished_at = now(), status = %s, rows_upserted = %s, "
        "fetch_ms = %s, parse_ms = %s, load_ms = %s, error = %s WHERE run_id = %s",
        (
            status,
            rows,
            times["fetch_ms"],
            times["parse_ms"],
            times["load_ms"],
            clean_error(error) if error else None,
            run_id,
        ),
    )


def last_value(conn: psycopg.Connection, table: str, column: str) -> date | int | None:
    """Return ``max(column)``; a ``YYYY-MM`` period becomes the first day of its month.

    Args:
        conn: Open connection.
        table: Table as ``schema.table``.
        column: Column holding a date, a ``YYYY-MM`` period or an integer year.

    Returns:
        The latest value, or ``None`` for an empty table.
    """
    query = sql.SQL("SELECT max({c}) FROM {t}").format(c=sql.Identifier(column), t=_table(table))
    row = conn.execute(query).fetchone()
    value = row[0] if row else None
    if isinstance(value, str):
        match = _PERIOD.match(value)
        if not match:
            raise ValueError(f"{table}.{column}: unexpected period {value!r}")
        return date(int(match[1]), int(match[2]), 1)
    result: date | int | None = value
    return result
