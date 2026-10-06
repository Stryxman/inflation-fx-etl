"""Database access: connection and idempotent schema creation."""

from pathlib import Path

import psycopg

SCHEMA_DIRS = ("raw", "audit")


def connect(dsn: str) -> psycopg.Connection:
    """Open a connection with autocommit disabled.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        An open connection; callers commit or roll back explicitly.
    """
    return psycopg.connect(dsn, autocommit=False)


def schema_files(root: Path) -> list[Path]:
    """List the schema files in application order.

    Args:
        root: Repository root.

    Returns:
        ``sql/00_schemas.sql``, then ``sql/raw/*.sql``, then ``sql/audit/*.sql``,
        each directory sorted by file name.
    """
    sql = root / "sql"
    files = [sql / "00_schemas.sql"]
    for directory in SCHEMA_DIRS:
        files.extend(sorted((sql / directory).glob("*.sql")))
    return files


def apply_schema(conn: psycopg.Connection, root: Path) -> list[str]:
    """Apply all schema files in a single transaction.

    Args:
        conn: Open connection.
        root: Repository root.

    Returns:
        Applied file paths relative to ``root``, in order.
    """
    applied: list[str] = []
    try:
        for path in schema_files(root):
            conn.execute(path.read_text(encoding="utf-8"))
            applied.append(path.relative_to(root).as_posix())
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return applied
