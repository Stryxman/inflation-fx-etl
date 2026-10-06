"""Source extractors: one module per source, sharing the contract in ``base``."""

from etl.extract import ecb_fx
from etl.extract.base import Extractor

EXTRACTORS: dict[str, Extractor] = {"ecb_fx": ecb_fx}
