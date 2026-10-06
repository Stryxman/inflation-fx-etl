"""Logging setup shared by the whole package."""

import logging
import sys
from urllib.parse import urlsplit, urlunsplit

ROOT = "etl"
FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup(level: str = "INFO") -> None:
    """Configure the ``etl`` root logger (stderr). Safe to call several times.

    Args:
        level: Logging level name, for example ``"INFO"`` or ``"DEBUG"``.
    """
    logger = logging.getLogger(ROOT)
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(FORMAT))
        logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger by name (use ``__name__``)."""
    return logging.getLogger(name)


def redact(url: str) -> str:
    """Remove the ``user:password@`` part of a URL so it can be logged safely.

    Args:
        url: Any URL, possibly with credentials.

    Returns:
        The same URL without credentials.
    """
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))
