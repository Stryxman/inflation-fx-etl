# Performance baseline

Reference measurements of the pipeline, taken from `audit.etl_runs` (`fetch_ms`, `parse_ms`,
`load_ms`). There is no threshold: the numbers exist to spot regressions and to size the
scheduled runs.

- Date: 2026-10-06 (first load 14:47, incremental load 14:48, local time)
- Machine: Linux x86_64, 8 logical CPUs, 14 GB RAM, PostgreSQL 17.11 in a local Docker
  container, residential internet connection
- Command: `make etl` (that is `python -m etl run`), twice in a row on an empty `etl` database
- Query: `select source, rows_upserted, fetch_ms, parse_ms, load_ms from audit.etl_runs order by run_id;` (runs 1–10 below; later runs append new rows)

## First load (empty database, history from 2015-01-01)

| Source | Rows | fetch_ms | parse_ms | load_ms |
|---|---:|---:|---:|---:|
| ecb_fx | 24080 | 1461 | 180 | 428 |
| ecb_hicp | 282 | 944 | 5 | 17 |
| oecd_cpi | 2238 | 8635 | 22 | 94 |
| wb_country | 8 | 144 | 0 | 3 |
| wb_inflation | 88 | 146 | 1 | 6 |

## Incremental load (second run, same day)

| Source | Rows | fetch_ms | parse_ms | load_ms |
|---|---:|---:|---:|---:|
| ecb_fx | 56 | 382 | 1 | 16 |
| ecb_hicp | 4 | 712 | 0 | 2 |
| oecd_cpi | 32 | 9073 | 1 | 15 |
| wb_country | 8 | 139 | 0 | 3 |
| wb_inflation | 8 | 435 | 0 | 2 |

Row counts after both runs are identical (`raw.ecb_fx` 24080, `raw.ecb_hicp` 282,
`raw.oecd_cpi` 2238, `raw.wb_country` 8, `raw.wb_inflation` 88): the second run only
re-upserts the overlap window.

## Reading the numbers

- Network time dominates: the database load is under half a second even for 24080 rows.
- `oecd_cpi` fetch time is mostly the mandatory 2 s pause between its four grouped requests
  (6 s of the total), which keeps the pipeline under the OECD rate limit.
