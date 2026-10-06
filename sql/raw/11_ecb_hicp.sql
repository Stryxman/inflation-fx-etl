-- ECB HICP monthly index (dataset HICP, never the frozen ICP).
CREATE TABLE IF NOT EXISTS raw.ecb_hicp (
    series text,
    period text CHECK (period ~ '^\d{4}-\d{2}$'),
    value numeric NOT NULL,
    obs_status text,
    _source text NOT NULL,
    _run_id bigint NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (series, period)
);
