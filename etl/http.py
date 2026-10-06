"""HTTP GET with timeout and bounded retries (5xx, 429 and network errors)."""

import time
from collections.abc import Callable
from typing import Any, Protocol

import requests

from etl.log import get_logger, redact

log = get_logger(__name__)


class _Response(Protocol):
    status_code: int
    content: bytes


class HttpClient(Protocol):
    """Minimal client: the ``requests`` module or a ``requests.Session``."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = ...,
        headers: dict[str, str] | None = ...,
        timeout: float = ...,
    ) -> _Response:
        """Perform a GET request."""
        ...


class FetchError(Exception):
    """A resource could not be fetched. The message never contains credentials."""


def get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    retries: int = 3,
    backoff: tuple[float, ...] = (1, 2, 4),
    session: HttpClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Fetch a URL and return the response body.

    Failures are logged at WARNING only; the caller (the pipeline) logs the ERROR.
    Retries on 5xx, 429 and network errors, waiting ``backoff[i]`` seconds before retry
    ``i``. Other 4xx responses fail immediately.

    Args:
        url: URL to fetch.
        params: Query parameters.
        headers: Request headers.
        timeout: Per-request timeout in seconds.
        retries: Number of retries after the first attempt.
        backoff: Delays in seconds before each retry.
        session: Object with a ``get`` method (defaults to the ``requests`` module).
        sleep: Function used to wait between attempts (injectable for tests).

    Returns:
        The response body.

    Raises:
        FetchError: On a non-retryable status, or when all attempts are used.
        ValueError: If ``retries`` is positive and ``backoff`` is empty.
    """
    if retries > 0 and not backoff:
        raise ValueError("backoff must contain at least one delay when retries > 0")
    client = session if session is not None else requests
    safe_url = redact(url)
    reason = ""
    for attempt in range(retries + 1):
        log.debug("GET %s", safe_url)
        try:
            response = client.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            reason = f"network error ({type(exc).__name__})"
        else:
            status = response.status_code
            if status < 400:
                return bytes(response.content)
            reason = f"HTTP {status}"
            if status < 500 and status != 429:
                message = f"GET {safe_url} failed: {reason}"
                log.warning(message)
                raise FetchError(message)
        if attempt < retries:
            delay = backoff[min(attempt, len(backoff) - 1)]
            log.warning(
                "GET %s: %s, retry %d/%d in %ss", safe_url, reason, attempt + 1, retries, delay
            )
            sleep(delay)
    message = f"GET {safe_url} failed after {retries + 1} attempts: {reason}"
    log.warning(message)
    raise FetchError(message)
