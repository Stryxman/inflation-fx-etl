import pytest

from etl.extract import EXTRACTORS
from etl.extract.base import Extractor

ALLOWED_LAST_TYPES = {"date", "month", "year"}


@pytest.mark.parametrize("name", sorted(EXTRACTORS))
def test_extractor_follows_contract(name):
    module = EXTRACTORS[name]
    for attr in ("SOURCE", "TABLE", "KEY", "LAST", "fetch", "parse"):
        assert hasattr(module, attr), attr
    assert module.SOURCE == name
    assert module.TABLE.startswith("raw.")
    assert module.KEY and all(isinstance(k, str) for k in module.KEY)
    assert module.LAST is None or module.LAST[1] in ALLOWED_LAST_TYPES
    assert callable(module.fetch) and callable(module.parse)
    assert isinstance(module, Extractor)
