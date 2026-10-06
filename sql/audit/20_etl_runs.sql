-- One row per source load; durations in milliseconds.
CREATE TABLE IF NOT EXISTS audit.etl_runs (
    run_id bigserial PRIMARY KEY,
    source text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    rows_upserted int,
    fetch_ms int,
    parse_ms int,
    load_ms int,
    error text
);
