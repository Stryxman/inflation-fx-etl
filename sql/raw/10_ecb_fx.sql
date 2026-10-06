-- ECB daily reference rates, units of currency per 1 EUR.
CREATE TABLE IF NOT EXISTS raw.ecb_fx (
    currency text,
    date date,
    rate numeric NOT NULL,
    obs_status text,
    _source text NOT NULL,
    _run_id bigint NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (currency, date)
);
