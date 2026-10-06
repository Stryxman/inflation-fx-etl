-- World Bank country reference data and annual inflation (null values kept as NULL).
CREATE TABLE IF NOT EXISTS raw.wb_country (
    iso3 text PRIMARY KEY,
    iso2 text NOT NULL,
    name text NOT NULL,
    income_level text,
    _source text NOT NULL,
    _run_id bigint NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.wb_inflation (
    iso3 text,
    year int,
    value numeric,
    _source text NOT NULL,
    _run_id bigint NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (iso3, year)
);
