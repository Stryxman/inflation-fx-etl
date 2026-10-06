-- OECD consumer prices: year-on-year rate and index, from two dataflows.
CREATE TABLE IF NOT EXISTS raw.oecd_cpi (
    ref_area text,
    measure text CHECK (measure IN ('yoy', 'index')),
    period text,
    value numeric NOT NULL,
    obs_status text,
    dataflow text NOT NULL,
    _source text NOT NULL,
    _run_id bigint NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ref_area, measure, period)
);
