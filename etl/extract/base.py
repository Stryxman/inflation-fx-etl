"""Shared pieces of the extractors.

Extractor contract
------------------
Every module in ``etl.extract`` (one per source) exposes::

    SOURCE: str            # source name, e.g. "ecb_fx"
    TABLE: str             # target table, e.g. "raw.ecb_fx"
    KEY: tuple[str, ...]   # primary-key columns, e.g. ("currency", "date")
    LAST: tuple[str, str] | None  # (column, type) giving the incremental start, or None
    def fetch(cfg: Config, since: date, get: Getter = etl.http.get) -> list[bytes]: ...
    def parse(payload: bytes) -> list[Row]: ...

``LAST`` type is one of ``"date"`` (a date column), ``"month"`` (a date column holding the
first day of a month; the extractor formats ``since`` with ``month_start``) or ``"year"``
(an integer year column). ``since_for`` turns the latest loaded value into the start date.
``None`` means the source is always fully reloaded.

``fetch`` performs the HTTP calls (``get`` is injectable) and returns one payload per
request. ``parse`` is pure: it turns one payload into rows holding exactly the business
columns of ``TABLE`` (no ``_source``, ``_run_id`` or ``_loaded_at``). It skips rows whose
value is empty or ``NaN`` (no row is created, nothing is interpolated), returns ``[]`` for a
header-only file, and raises ``ParseError`` with an explicit message when the payload is not
the expected format (missing columns, HTML error page, empty body).

Rows are typed ``Row = dict[str, object]``: the column set differs per source, and the
loader only forwards values to the database driver.
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from etl.config import Config

FLOOR = date(2015, 1, 1)
LAST_TYPES = frozenset({"date", "month", "year"})

Row = dict[str, object]


class Getter(Protocol):
    """HTTP function used by ``fetch`` (``etl.http.get`` or a test double)."""

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        """Return the body of ``url``."""
        ...


@runtime_checkable
class Extractor(Protocol):
    """Shape of an extractor module (see the module docstring)."""

    SOURCE: str
    TABLE: str
    KEY: tuple[str, ...]
    LAST: tuple[str, str] | None

    def fetch(self, cfg: "Config", since: date, get: Getter = ...) -> list[bytes]:
        """Download the raw payloads from ``since`` on."""
        ...

    def parse(self, payload: bytes) -> list[Row]:
        """Turn one payload into rows."""
        ...


class ParseError(Exception):
    """The payload of a source does not have the expected format."""


def start_from(last: date | None, floor: date = date(2015, 1, 1), overlap_days: int = 10) -> date:
    """Compute the start date of an extraction.

    Args:
        last: Latest date already loaded, or ``None`` for an empty table.
        floor: Earliest date ever requested.
        overlap_days: Days re-fetched before ``last`` to pick up revisions.

    Returns:
        ``floor`` when ``last`` is ``None``, else ``max(floor, last - overlap_days)``.
    """
    if last is None:
        return floor
    return max(floor, last - timedelta(days=overlap_days))


def month_start(d: date) -> str:
    """Format a date as the ``YYYY-MM`` month that contains it."""
    return f"{d.year:04d}-{d.month:02d}"


def since_for(last: date | int | None, sql_type: str) -> date:
    """Compute the extraction start from the latest loaded value.

    Args:
        last: Latest loaded value: a ``date`` for ``"date"``/``"month"``, an ``int`` year
            for ``"year"``, or ``None`` for an empty table.
        sql_type: One of ``"date"``, ``"month"`` or ``"year"`` (second item of ``LAST``).

    Returns:
        ``FLOOR`` for an empty table. For ``"date"`` and ``"month"``, ``start_from(last)``
        (for ``"month"`` the extractor then applies ``month_start``). For ``"year"``, January
        1st of ``last`` without overlap, never before ``FLOOR``.

    Raises:
        ValueError: If ``sql_type`` is unknown.
        TypeError: If ``last`` does not match ``sql_type``.
    """
    if sql_type not in LAST_TYPES:
        raise ValueError(f"unknown LAST type {sql_type!r}, expected one of {sorted(LAST_TYPES)}")
    if last is None:
        return FLOOR
    if sql_type == "year":
        if not isinstance(last, int) or isinstance(last, date):
            raise TypeError(f"'year' expects an int, got {type(last).__name__}")
        return max(FLOOR, date(last, 1, 1))
    if not isinstance(last, date):
        raise TypeError(f"{sql_type!r} expects a date, got {type(last).__name__}")
    return start_from(last)
