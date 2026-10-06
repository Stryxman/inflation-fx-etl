"""Command line: ``python -m etl run | extract [source] | transform | check``."""

import argparse

import psycopg

from etl.config import load_config
from etl.db import apply_schema, connect
from etl.extract import EXTRACTORS
from etl.load.raw_loader import clean_error
from etl.log import get_logger, setup
from etl.pipeline import RunResult, run_all
from etl.transform.runner import run_layers

log = get_logger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etl", description="Inflation and FX ETL pipeline")
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="create the schema, extract and load all sources, transform")
    extract = sub.add_parser("extract", help="extract and load, without transformations")
    extract.add_argument("source", nargs="?", choices=list(EXTRACTORS))
    sub.add_parser("transform", help="apply the SQL transformation layers")
    sub.add_parser("check", help="apply the data quality checks")
    return parser


def _print_summary(results: list[RunResult]) -> None:
    for r in results:
        t = r.timings
        print(
            f"{r.source:<14} {r.status:<8} rows={r.rows:<6} "
            f"fetch_ms={t.get('fetch_ms', '-')} parse_ms={t.get('parse_ms', '-')} "
            f"load_ms={t.get('load_ms', '-')}" + (f"  error: {r.error}" if r.error else "")
        )


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; ``sys.argv`` when ``None``.

    Returns:
        ``1`` if a source failed or the database is unreachable, else ``0``.
    """
    args = _parser().parse_args(argv)
    setup(args.log_level)
    cfg = load_config()
    sql_dir = cfg.root / "sql"
    if args.command == "check" and not (sql_dir / "checks").is_dir():
        print("no checks defined yet")
        return 0
    try:
        with connect(cfg.dsn) as conn:
            if args.command == "check":
                run_layers(conn, sql_dir, ("checks",))
                return 0
            failed = False
            if args.command in ("run", "extract"):
                apply_schema(conn, cfg.root)
                names = [args.source] if args.command == "extract" and args.source else None
                results = run_all(conn, cfg, names=names)
                _print_summary(results)
                failed = any(r.status == "failed" for r in results)
            if args.command in ("run", "transform"):
                run_layers(conn, sql_dir)
            return 1 if failed else 0
    except psycopg.Error as exc:
        log.error("database error: %s", clean_error(f"{type(exc).__name__}: {exc}"))
        return 1
