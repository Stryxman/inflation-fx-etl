"""Apply the SQL transformation layers (``sql/staging``, ``sql/mart``, ``sql/checks``)."""

from pathlib import Path

import psycopg

from etl.log import get_logger

log = get_logger(__name__)

LAYERS = ("staging", "mart", "checks")


def run_layers(
    conn: psycopg.Connection, sql_dir: Path, layers: tuple[str, ...] = LAYERS
) -> list[str]:
    """Run the ``*.sql`` files of each layer, one transaction per layer.

    A layer whose directory does not exist is skipped. When a file fails, its layer is
    rolled back, earlier layers stay applied, and the exception propagates.

    Args:
        conn: Open connection.
        sql_dir: Directory that holds one sub-directory per layer.
        layers: Layer names, in application order.

    Returns:
        Applied files as ``layer/name.sql``, in order.
    """
    applied: list[str] = []
    for layer in layers:
        directory = sql_dir / layer
        if not directory.is_dir():
            log.debug("layer %s: no directory, skipped", layer)
            continue
        done: list[str] = []
        try:
            for path in sorted(directory.glob("*.sql")):
                conn.execute(path.read_text(encoding="utf-8"))
                done.append(f"{layer}/{path.name}")
        except Exception:
            conn.rollback()
            log.error("layer %s failed and was rolled back", layer)
            raise
        conn.commit()
        log.info("layer %s: applied %d file(s)", layer, len(done))
        applied.extend(done)
    return applied
