"""Run extractors one by one: fetch, parse, load, with one journal row per source."""

import time
from dataclasses import dataclass, field

import psycopg

import etl.http
from etl.config import Config
from etl.extract import EXTRACTORS
from etl.extract.base import Extractor, Getter, Row, since_for
from etl.load import raw_loader
from etl.log import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class RunResult:
    """Outcome of one source run."""

    source: str
    status: str
    rows: int
    error: str | None
    timings: dict[str, int] = field(default_factory=dict)


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def run_source(
    conn: psycopg.Connection,
    cfg: Config,
    ext: Extractor,
    get: Getter = etl.http.get,
) -> RunResult:
    """Load one source. The data and the ``success`` journal update share one transaction.

    On any error the transaction is rolled back (no partial rows) and the journal row is
    closed as ``failed`` in a separate transaction.

    Args:
        conn: Open connection.
        cfg: Pipeline configuration.
        ext: Extractor module.
        get: HTTP function (injectable for tests).

    Returns:
        The result; failures are reported in it, not raised.
    """
    name = ext.SOURCE
    run_id = raw_loader.start_run(conn, name)
    timings: dict[str, int] = {}
    try:
        last = raw_loader.last_value(conn, ext.TABLE, ext.LAST[0]) if ext.LAST else None
        since = since_for(last, ext.LAST[1] if ext.LAST else "date")
        log.info("%s: start since=%s", name, since.isoformat())

        t0 = time.perf_counter()
        payloads = ext.fetch(cfg, since, get)
        timings["fetch_ms"] = _ms(t0)
        log.info("%s: fetched %d payload(s) in %d ms", name, len(payloads), timings["fetch_ms"])

        t0 = time.perf_counter()
        rows: list[Row] = []
        for payload in payloads:
            rows.extend(ext.parse(payload))
        timings["parse_ms"] = _ms(t0)
        log.debug("%s: parsed %d rows in %d ms", name, len(rows), timings["parse_ms"])

        t0 = time.perf_counter()
        count = raw_loader.upsert(conn, ext.TABLE, rows, ext.KEY, run_id, name)
        timings["load_ms"] = _ms(t0)
        raw_loader.finish_run(conn, run_id, "success", count, timings=timings)
        conn.commit()
        log.info("%s: upserted %d rows in %d ms", name, count, timings["load_ms"])
        return RunResult(name, "success", count, None, timings)
    except Exception as exc:
        conn.rollback()
        message = raw_loader.clean_error(f"{type(exc).__name__}: {exc}")
        log.error("%s: failed: %s", name, message)
        raw_loader.finish_run(conn, run_id, "failed", 0, error=message, timings=timings)
        conn.commit()
        return RunResult(name, "failed", 0, message, timings)


def run_all(
    conn: psycopg.Connection,
    cfg: Config,
    names: list[str] | None = None,
    get: Getter = etl.http.get,
) -> list[RunResult]:
    """Load several sources; a failing source does not stop the next ones.

    Args:
        conn: Open connection.
        cfg: Pipeline configuration.
        names: Source names to run; all sources, in registry order, when ``None``.
        get: HTTP function (injectable for tests).

    Returns:
        One result per source, in run order.

    Raises:
        ValueError: If a name is not a registered source.
    """
    selected = names if names is not None else list(EXTRACTORS)
    for name in selected:
        if name not in EXTRACTORS:
            raise ValueError(f"unknown source {name!r}, expected one of {list(EXTRACTORS)}")
    return [run_source(conn, cfg, EXTRACTORS[name], get) for name in selected]
