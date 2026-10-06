import logging

from etl import log


def _handlers() -> list[logging.Handler]:
    return logging.getLogger("etl").handlers


def test_setup_twice_keeps_one_handler():
    log.setup()
    log.setup()
    assert len(_handlers()) == 1


def test_setup_sets_level():
    log.setup("DEBUG")
    assert logging.getLogger("etl").level == logging.DEBUG
    log.setup("INFO")
    assert logging.getLogger("etl").level == logging.INFO


def test_get_logger_returns_named_logger():
    assert log.get_logger("etl.x").name == "etl.x"


def test_redact_removes_credentials():
    out = log.redact("postgresql://etl:secret@localhost/etl")
    assert "secret" not in out
    assert "etl:" not in out
    assert out == "postgresql://localhost/etl"


def test_redact_leaves_plain_url_untouched():
    assert log.redact("https://example.org/a?b=1") == "https://example.org/a?b=1"
