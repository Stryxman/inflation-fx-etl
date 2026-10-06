import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from etl import cli
from etl.config import Config
from etl.pipeline import RunResult


@pytest.fixture(autouse=True)
def fresh_etl_logger() -> Iterator[None]:
    """Let ``setup`` attach a handler to the current (captured) stderr, then restore."""
    logger = logging.getLogger("etl")
    handlers, level = list(logger.handlers), logger.level
    logger.handlers.clear()
    yield
    logger.handlers[:] = handlers
    logger.setLevel(level)


TIMINGS = {"fetch_ms": 12, "parse_ms": 3, "load_ms": 40}


def result(source: str, status: str) -> RunResult:
    return RunResult(source, status, 5 if status == "success" else 0, None, TIMINGS)


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    mocks = {
        "connect": MagicMock(),
        "apply_schema": MagicMock(return_value=[]),
        "run_all": MagicMock(return_value=[result("a", "success")]),
        "run_layers": MagicMock(return_value=[]),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(f"etl.cli.{name}", mock)
    return mocks


def test_cli_exit_code_1_when_a_source_fails(
    patched: dict[str, MagicMock], capsys: pytest.CaptureFixture[str]
) -> None:
    patched["run_all"].return_value = [result("a", "success"), result("b", "failed")]
    assert cli.main(["run"]) == 1
    out = capsys.readouterr().out
    assert "a" in out and "success" in out and "failed" in out
    assert "fetch_ms=12" in out and "parse_ms=3" in out and "load_ms=40" in out


def test_cli_run_exit_0_and_order(patched: dict[str, MagicMock]) -> None:
    assert cli.main(["run"]) == 0
    patched["apply_schema"].assert_called_once()
    patched["run_all"].assert_called_once()
    assert patched["run_all"].call_args.kwargs.get("names") is None
    patched["run_layers"].assert_called_once()


def test_cli_extract_with_source_skips_transform(patched: dict[str, MagicMock]) -> None:
    assert cli.main(["extract", "ecb_fx"]) == 0
    assert patched["run_all"].call_args.kwargs["names"] == ["ecb_fx"]
    patched["run_layers"].assert_not_called()


def test_cli_extract_rejects_unknown_source(
    patched: dict[str, MagicMock], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["extract", "nope"])
    assert exc.value.code == 2
    assert "invalid choice: 'nope'" in capsys.readouterr().err


def test_cli_transform_runs_layers_only(patched: dict[str, MagicMock]) -> None:
    patched["run_layers"].return_value = ["staging/10_a.sql"]
    assert cli.main(["transform"]) == 0
    patched["run_all"].assert_not_called()


def test_cli_check_without_checks_layer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cfg: Config,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "etl.cli.load_config", lambda: cfg.__class__(**{**cfg.__dict__, "root": tmp_path})
    )
    assert cli.main(["check"]) == 0
    assert "no checks defined yet" in capsys.readouterr().out


def test_cli_log_level_debug_enables_debug_logs(patched: dict[str, MagicMock]) -> None:
    logger = logging.getLogger("etl")
    before = logger.level
    try:
        cli.main(["--log-level", "DEBUG", "transform"])
        assert logger.level == logging.DEBUG
        cli.main(["transform"])
        assert logger.level == logging.INFO
    finally:
        logger.setLevel(before)


def test_cli_database_unreachable_exits_1(
    patched: dict[str, MagicMock], capsys: pytest.CaptureFixture[str]
) -> None:
    import psycopg

    patched["connect"].side_effect = psycopg.OperationalError(
        "connection to postgresql://etl:etl_local_only@localhost/etl failed"
    )
    assert cli.main(["run"]) == 1
    captured = capsys.readouterr()
    assert "etl_local_only" not in captured.out + captured.err
