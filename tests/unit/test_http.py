import logging
from typing import Any

import pytest
import requests

from etl import http


class FakeResponse:
    def __init__(self, status: int, content: bytes = b"ok") -> None:
        self.status_code = status
        self.content = content


class FakeSession:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kw: Any) -> FakeResponse:
        self.calls.append({"url": url, **kw})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def run(outcomes, **kw):
    sleeps: list[float] = []
    session = FakeSession(outcomes)
    result = http.get("https://example.org/x", session=session, sleep=sleeps.append, **kw)
    return result, session, sleeps


def test_success_no_sleep_and_debug_log(caplog):
    caplog.set_level(logging.DEBUG, logger="etl")
    result, session, sleeps = run([FakeResponse(200, b"data")])
    assert result == b"data"
    assert sleeps == []
    assert len(session.calls) == 1
    assert "GET https://example.org/x" in caplog.text


def test_retry_logs_warning_with_status_and_delay(caplog):
    caplog.set_level(logging.WARNING, logger="etl")
    run([FakeResponse(503), FakeResponse(200)])
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "503" in warnings[0].getMessage()
    assert "in 1s" in warnings[0].getMessage()


def test_503_503_200_gives_three_calls_and_delays():
    result, session, sleeps = run([FakeResponse(503), FakeResponse(503), FakeResponse(200)])
    assert result == b"ok"
    assert len(session.calls) == 3
    assert sleeps == [1, 2]


def test_429_four_times_fails_after_four_calls():
    sleeps: list[float] = []
    session = FakeSession([FakeResponse(429)] * 4)
    with pytest.raises(http.FetchError):
        http.get("https://example.org/x", session=session, sleep=sleeps.append)
    assert len(session.calls) == 4
    assert sleeps == [1, 2, 4]


def test_404_fails_immediately():
    session = FakeSession([FakeResponse(404)])
    sleeps: list[float] = []
    with pytest.raises(http.FetchError, match="404"):
        http.get("https://example.org/x", session=session, sleep=sleeps.append)
    assert len(session.calls) == 1
    assert sleeps == []


def test_connection_error_then_success():
    result, session, sleeps = run([requests.ConnectionError("boom"), FakeResponse(200)])
    assert result == b"ok"
    assert sleeps == [1]


def test_connection_error_exhausted_raises_fetch_error():
    with pytest.raises(http.FetchError):
        http.get(
            "https://example.org/x",
            session=FakeSession([requests.Timeout("t")] * 4),
            sleep=lambda s: None,
        )


def test_timeout_params_headers_forwarded():
    _, session, _ = run([FakeResponse(200)], params={"a": "1"}, headers={"H": "v"})
    call = session.calls[0]
    assert call["timeout"] == 30
    assert call["params"] == {"a": "1"}
    assert call["headers"] == {"H": "v"}


def test_error_message_has_no_credentials():
    session = FakeSession([FakeResponse(404)])
    with pytest.raises(http.FetchError) as exc:
        http.get("https://user:secret@example.org/x", session=session, sleep=lambda s: None)
    assert "secret" not in str(exc.value)


def test_default_session_is_requests_module(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        return FakeResponse(200, b"z")

    monkeypatch.setattr(requests, "get", fake_get)
    assert http.get("https://example.org/y") == b"z"
    assert seen["url"] == "https://example.org/y"


def test_no_secret_in_any_log_level(caplog):
    caplog.set_level(logging.DEBUG, logger="etl")
    url = "https://user:secret@example.org/x"
    with pytest.raises(http.FetchError):
        http.get(
            url, session=FakeSession([FakeResponse(503), FakeResponse(404)]), sleep=lambda s: None
        )
    with pytest.raises(http.FetchError):
        http.get(
            url,
            retries=1,
            session=FakeSession([requests.ConnectionError("secret")] * 2),
            sleep=lambda s: None,
        )
    assert caplog.records
    assert "secret" not in caplog.text


def test_empty_backoff_with_retries_is_rejected():
    with pytest.raises(ValueError, match="backoff"):
        http.get("https://example.org/x", backoff=(), session=FakeSession([]))


def test_empty_backoff_without_retries_is_fine():
    session = FakeSession([FakeResponse(200)])
    assert http.get("https://example.org/x", retries=0, backoff=(), session=session) == b"ok"
