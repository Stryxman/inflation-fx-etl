"""Configuration loading: country scope, data sources and database connection strings."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

TEST_DB = "etl_test"


@dataclass(frozen=True)
class Country:
    """A tracked country."""

    iso3: str
    iso2: str
    currency: str
    group: str


@dataclass(frozen=True)
class Series:
    """Monthly inflation series of one territory.

    ``source`` and ``key`` are ``None`` and ``fallback`` is ``"worldbank_annual"`` when the
    territory relies on the annual World Bank fallback.
    """

    territory: str
    source: str | None
    key: str | None
    index_key: str | None
    freq: str
    covered_from: str | None
    covered_until: str | None
    fallback: str | None


@dataclass(frozen=True)
class Config:
    """Full pipeline configuration."""

    root: Path
    countries: list[Country]
    reference: str
    sources: dict[str, dict[str, Any]]
    inflation: dict[str, Series]
    dsn: str = field(repr=False)
    test_dsn: str = field(repr=False)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping at the top level")
    return data


def _dsn(database: str | None = None) -> str:
    """Build a connection string from the environment, with local defaults."""
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = quote(os.environ.get("POSTGRES_USER", "etl"), safe="")
    password = quote(os.environ.get("POSTGRES_PASSWORD", "etl_local_only"), safe="")
    name = database or os.environ.get("POSTGRES_DB", "etl")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def load_config(root: Path | None = None) -> Config:
    """Load the configuration from ``config/*.yaml`` and the environment.

    Args:
        root: Repository root. Defaults to the parent of the ``etl`` package.

    Returns:
        The immutable configuration.
    """
    root = root or Path(__file__).resolve().parents[1]
    countries_cfg = _load_yaml(root / "config" / "countries.yaml")
    sources_cfg = _load_yaml(root / "config" / "sources.yaml")

    countries = [Country(**c) for c in countries_cfg["countries"]]
    inflation = {
        code: Series(
            territory=code,
            source=spec.get("source"),
            key=spec.get("key"),
            index_key=spec.get("index_key"),
            freq=spec["freq"],
            covered_from=spec.get("covered_from"),
            covered_until=spec.get("covered_until"),
            fallback=spec.get("fallback"),
        )
        for code, spec in sources_cfg["inflation"].items()
    }
    sources = {name: block for name, block in sources_cfg.items() if name != "inflation"}

    return Config(
        root=root,
        countries=countries,
        reference=countries_cfg["reference"]["code"],
        sources=sources,
        inflation=inflation,
        dsn=_dsn(),
        test_dsn=_dsn(TEST_DB),
    )
