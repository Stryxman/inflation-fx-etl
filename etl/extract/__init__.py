"""Source extractors: one module per source, sharing the contract in ``base``."""

from etl.extract import ecb_fx, ecb_hicp, oecd_cpi, worldbank
from etl.extract.base import Extractor

EXTRACTORS: dict[str, Extractor] = {
    "ecb_fx": ecb_fx,
    "ecb_hicp": ecb_hicp,
    "oecd_cpi": oecd_cpi,
    "wb_country": worldbank.COUNTRY,
    "wb_inflation": worldbank.INFLATION,
}
