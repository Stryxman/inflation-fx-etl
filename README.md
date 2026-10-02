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

M0 scoping completed on 2026-10-02 (charter v1.0 approved). M1 (Extract + Load) is next. No application code yet. See [PROGRESS.md](PROGRESS.md).

## Documents

| Document | Content |
|---|---|
| [docs/project-charter.md](docs/project-charter.md) | Context, objectives, scope, indicators, organisation, success criteria |
| [docs/decisions.md](docs/decisions.md) | Decision log (D1–D14) |
| [docs/risks.md](docs/risks.md) | Risk register (R1–R8) |
| [docs/sources.md](docs/sources.md) | Data sources, licences, coverage and technical notes |
| [PROGRESS.md](PROGRESS.md) | Task tracking and project log |
| [config/countries.yaml](config/countries.yaml) | Country scope |
| [config/sources.yaml](config/sources.yaml) | Source URLs and selected series |

## Prerequisites

- Docker
- Python 3.12+

There are no installation steps yet; they will be added with the infrastructure milestone (M1).
