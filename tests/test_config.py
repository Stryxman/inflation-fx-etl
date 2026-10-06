from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from etl.config import load_config

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = ("PGHOST", "PGPORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")


def test_every_territory_has_monthly_key_or_fallback():
    cfg = load_config(ROOT)
    for code in [c.iso3 for c in cfg.countries] + [cfg.reference]:
        s = cfg.inflation[code]
        assert s.key or s.fallback == "worldbank_annual", code


def test_each_series_source_is_a_declared_block():
    cfg = load_config(ROOT)
    for s in cfg.inflation.values():
        if s.source is not None:
            assert s.source in cfg.sources, (s.territory, s.source)


def test_hicp_never_uses_frozen_icp_dataset():
    cfg = load_config(ROOT)
    assert "/HICP/" in cfg.sources["ecb_hicp"]["url"]
    assert "/ICP/" not in cfg.sources["ecb_hicp"]["url"]


def test_dsn_defaults_and_env_override(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    assert load_config(ROOT).dsn == "postgresql://etl:etl_local_only@localhost:5432/etl"
    monkeypatch.setenv("PGPORT", "5555")
    cfg = load_config(ROOT)
    assert cfg.dsn.endswith("@localhost:5555/etl")
    assert cfg.test_dsn.endswith("@localhost:5555/etl_test")


def test_eight_countries_four_per_group():
    groups = [c.group for c in load_config(ROOT).countries]
    assert len(groups) == 8 and groups.count("developed") == 4 and groups.count("emerging") == 4


def test_default_root_is_repository_root():
    assert load_config().root == ROOT


def test_inflation_block_is_not_a_source():
    assert "inflation" not in load_config(ROOT).sources


def test_series_fields_are_loaded():
    s = load_config(ROOT).inflation["USA"]
    assert (s.territory, s.source, s.freq) == ("USA", "oecd_cpi", "M")
    assert s.index_key and s.covered_from == "2015-01" and s.fallback is None


def test_fallback_territory_has_no_source_or_key(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "countries.yaml").write_text(
        "countries:\n  - {iso3: USA, iso2: US, currency: USD, group: developed}\n"
        "reference: {code: EA, currency: EUR}\n"
    )
    (tmp_path / "config" / "sources.yaml").write_text(
        "inflation:\n  USA: {fallback: worldbank_annual, freq: A}\n"
    )
    s = load_config(tmp_path).inflation["USA"]
    assert s.source is None and s.key is None and s.fallback == "worldbank_annual"


def test_repr_does_not_leak_password(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "distinctive-pw-9137")
    cfg = load_config(ROOT)
    assert "distinctive-pw-9137" in cfg.dsn
    assert "distinctive-pw-9137" not in repr(cfg)


def test_dsn_encodes_special_characters(monkeypatch):
    for v in ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:w/rd")
    monkeypatch.setenv("POSTGRES_USER", "us@er")
    parts = urlsplit(load_config(ROOT).dsn)
    assert parts.password is not None and unquote(parts.password) == "p@ss:w/rd"
    assert parts.username is not None and unquote(parts.username) == "us@er"
    assert parts.hostname == "localhost" and parts.port == 5432


@pytest.mark.db
def test_db_fixture_gives_a_clean_test_database(db):
    schemas = {r[0] for r in db.execute("SELECT schema_name FROM information_schema.schemata")}
    assert not schemas & {"raw", "staging", "mart", "audit"}
