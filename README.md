# inflation-fx-etl

An ETL pipeline that crosses inflation and exchange rates for 8 countries against the euro.

## Problem and question

An analyst monitoring the currency exposure of holdings spread across emerging-market and developed-market currencies needs to know whether currency moves are consistent with inflation.

**Question tracked:** when a country's inflation exceeds that of the euro area, does its currency depreciate against the euro by a comparable amount?

The pipeline collects public data (ECB, OECD, World Bank), loads it into PostgreSQL, transforms it in SQL, and shows the result in a Grafana dashboard.

## Architecture

```
 [ECB CSV]  [OECD SDMX-CSV]  [World Bank JSON]
      \            |                /
   EXTRACT  (Python: requests, 3 retries, incremental)
                   |
   LOAD  ->  raw.*        (data as received + _source, _loaded_at, _run_id; UPSERT)
                   |
   TRANSFORM  (versioned sql/**/*.sql files, run in alphabetical order)
        staging.*  -> types, harmonised ISO3 codes, deduplication, union with fallback values
        mart.*     -> derived indicators
        checks     -> mart.data_quality
                   |
   PostgreSQL 17  --  Grafana (datasource and dashboard provisioned from files)
   audit.etl_runs: one row per source and per run
```

## Status

M0 scoping completed on 2026-10-02 (charter v1.0 approved). M1 (Extract + Load) in progress: local infrastructure, project tooling and CI first. See [PROGRESS.md](PROGRESS.md).

## Documents

| Document | Content |
|---|---|
| [docs/project-charter.md](docs/project-charter.md) | Context, objectives, scope, indicators, organisation, success criteria |
| [docs/decisions.md](docs/decisions.md) | Decision log (D1–D15) |
| [docs/risks.md](docs/risks.md) | Risk register (R1–R8) |
| [docs/sources.md](docs/sources.md) | Data sources, licences, coverage and technical notes |
| [docs/performance.md](docs/performance.md) | Reference performance measurements of the pipeline |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Naming, test, log and commit conventions |
| [PROGRESS.md](PROGRESS.md) | Task tracking and project log |
| [config/countries.yaml](config/countries.yaml) | Country scope |
| [config/sources.yaml](config/sources.yaml) | Source URLs and selected series |

## Prerequisites

- Docker
- Python 3.12+
- GNU Make

## Getting started

```bash
make venv                # create .venv and install the package with dev tools
cp .env.example .env     # local values only; edit if a port is already in use
make up                  # start PostgreSQL 17 and Grafana (http://localhost:3000)
make test                # run the tests (database tests need `make up`)
make lint                # ruff and mypy
```

`make down` stops the containers; `make reset` also deletes their data.

Load the data (history since 2015-01-01 on the first run, then incremental):

```bash
make etl            # extract all sources into raw.* and log each run in audit.etl_runs
.venv/bin/python -m etl --log-level DEBUG run   # same, with detailed logs
make transform      # apply the SQL layers (staging, mart; added in M2)
make check          # data quality checks (added in M2)
```

Reference timings of a full and an incremental load are in [docs/performance.md](docs/performance.md).
