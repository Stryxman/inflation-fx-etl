# Project charter — Inflation × Exchange Rate ETL

- **Version:** 1.0
- **Date:** 2026-10-02
- **Status:** Draft — pending project lead approval at the M0 milestone review
- **Author:** Richard (project lead), with an AI coding assistant

## 1. Context and question tracked

Currency exposure in a set of foreign-currency holdings depends on how each currency moves against the investor's reference currency, and inflation differentials are a classic explanation for those moves. This project builds a data pipeline that makes the relationship observable, country by country, in a single dashboard.

**The question tracked:** when a country's inflation exceeds that of the euro area, does its currency depreciate against the euro by a comparable amount?

## 2. Objectives

1. Collect several heterogeneous public data sources (exchange rates, consumer price indices, country metadata) automatically.
2. Load them as received into PostgreSQL, then transform them in SQL (ELT) into documented, tested indicators.
3. Present the result in a dynamic dashboard that lets an analyst compare countries and groups.
4. Make the pipeline reliable: re-runnable without duplicates, tolerant to the failure of one source, with visible data quality and freshness checks.

## 3. Users

An analyst who monitors the currency exposure of holdings spread across emerging-market and developed-market currencies. They want to see, for each country, whether recent currency moves are consistent with inflation differentials, and whether the underlying data is fresh and trustworthy.

## 4. Scope

### 4.1 Sources

Countries are defined in `config/countries.yaml`; the reference is the euro area (internal code `EA`, currency EUR).

| Group | ISO3 | Currency |
|---|---|---|
| Developed | USA | USD |
| Developed | GBR | GBP |
| Developed | JPN | JPY |
| Developed | CHE | CHF |
| Emerging | TUR | TRY |
| Emerging | BRA | BRL |
| Emerging | IND | INR |
| Emerging | ZAF | ZAR |

The group (developed or emerging) is fixed in the configuration. The World Bank income level is loaded as complementary information but does not determine the group.

| ID | Source | Content | Format | Frequency |
|---|---|---|---|---|
| `ecb_fx` | ECB, EXR dataset, `D.{currencies}.EUR.SP00.A` | Units of foreign currency per 1 EUR | CSV | Daily, business days |
| `ecb_hicp` | ECB, HICP dataset, euro area (key provider `4D0`) | Year-on-year inflation (`ANR`) and price index (`INX`) | CSV | Monthly |
| `oecd_cpi` | OECD SDMX, `DSD_PRICES@DF_PRICES_ALL` (legacy dataflow) | CPI: year-on-year inflation (`GY`) and index (`IX`) for USA, GBR, BRA, IND | SDMX-CSV | Monthly |
| `oecd_cpi_c2018` | OECD SDMX, `DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL` (COICOP 2018 dataflow) | Same measures for JPN, CHE, TUR, ZAF | SDMX-CSV | Monthly |
| `worldbank` | World Bank API v2 | Country metadata and annual inflation `FP.CPI.TOTL.ZG` (dormant fallback, see [decision D11](decisions.md)) | JSON | Annual |

The series keys and covered periods are fixed in `config/sources.yaml` and documented in [sources.md](sources.md).

Known gap: the USA has no CPI value for 2025-10 at the source. The month is kept empty (no interpolation); every indicator that depends on it is null for that month, and the pipeline and dashboard must tolerate such nulls.

### 4.2 Pipeline

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

Raw data is loaded before being transformed, and all transformation is written in SQL inside the database (ELT): `raw` -> `staging` -> `mart`.

### 4.3 Indicators

Exchange rates are expressed as units of foreign currency per 1 EUR.

| Object | Grain | Definition |
|---|---|---|
| `mart.fx_monthly` | country × month | `avg(rate)` over the quoted days of the month |
| `mart.fx_yoy` | country × month | `(rate_m / rate_{m-12} - 1) × 100`. Because the rate is units of currency per 1 EUR, **a positive value means the currency is depreciating** against the euro. |
| `mart.inflation_gap` | country × month | `yoy_pct(country) - yoy_pct(EA)` |
| `mart.ppp_gap` | country × month | `100 × (fx_m / fx_base) ÷ [(cpi_m / cpi_base) ÷ (cpiEA_m / cpiEA_base)]`, base = 2015-01. **100**: the depreciation is exactly what inflation justifies. **> 100**: the currency has fallen more than inflation justifies. **< 100**: it has fallen less. |
| `mart.data_quality` | one check per row | `check_name, severity (block\|warn), failing_rows, checked_at` |

For `ppp_gap`, each price index is divided by its own value in 2015-01 (ratios of indices relative to 2015-01). The index base year (2015 for the OECD, 2025 for the ECB) therefore has no effect on the result.

If a month comes from the dormant annual fallback (`is_fallback`), its price index is rebuilt by compounding the annual rates, and the resulting rows keep `is_fallback = true`.

Quality checks (`sql/checks`):

- no duplicates on the `staging` keys (block);
- no null or non-positive `rate` (block);
- latest exchange rate less than 5 business days old (warn);
- latest CPI less than 3 months old, per country (warn) — this is also how a series that stopped advancing after an API migration is detected, without storing the previous run's state;
- share of fallback values per country (warn if > 0).

### 4.4 Dashboard

Grafana dashboard "Inflation × FX", provisioned automatically from `grafana/dashboards/inflation_fx.json`.

- **Variables:** `$group` (developed or emerging) and `$country` (multi-select, filtered by `$group`).
- **Panels:**
  1. Exchange rate rebased to 100 at the start of the displayed period (daily time series).
  2. Year-on-year inflation of the selected countries, with the euro area dashed.
  3. Scatter plot for the latest available month: inflation gap (X) against `fx_yoy` (Y), one point per country.
  4. `ppp_gap` index, with a reference line at 100.
- Points derived from the fallback (`is_fallback`) are visibly marked on panels 2 and 4.
  5. Pipeline health: latest run per source, status, rows loaded, and failing quality checks.
- Automatic refresh every 5 minutes. The default period covers the last 5 years.

### 4.5 Robustness

- **Incremental loading:** `since = max(date in raw.<table>) - 10 days`, or 2015-01-01 if the table is empty; annual World Bank series reload the last loaded year and any newer year. The overlap captures revisions, and the UPSERT prevents duplicates.
- **HTTP:** 30 s maximum per request; 3 retries with increasing delay (1 s, 2 s, 4 s) for 5xx errors, 429 and network errors.
- **Source isolation:** if a source fails, `audit.etl_runs.status = failed` is written with the error message and the other sources continue. The transformation runs on the available data. The CLI exits with code 1 if at least one source failed.
- **Transactions:** a failure in a layer rolls back the whole layer; the `mart` views keep their previous state.
- **Commands:** `make up`, `down`, `etl`, `transform`, `check`, `test`, `psql`, `reset`. `tests/test_config.py` checks that `config/sources.yaml` covers every territory.
- **Scheduling:** manual trigger (`make etl`) in V1. The README provides an optional daily cron line.
- **Testing:** unit tests on each `parse()`, SQL tests with exact expected values, integration test with two runs and mocked HTTP; each test is written before the code (TDD).

## 5. Out of scope

- Cryptocurrencies (planned for V2 as a third source).
- Orchestrators (Airflow, Dagster) and dbt.
- Cloud deployment. Everything runs locally.

## 6. Constraints

- Everything runs locally, with PostgreSQL and Grafana under Docker.
- Free data sources only, with no API key.
- Python 3.12+ pipeline running on the host in a virtual environment.
- Docker must be installed on the machine (prerequisite).
- All public content is written in English.

## 7. Organisation

### Milestones

| Milestone | Content |
|---|---|
| M0 — Scoping | Steering documents, source verification, repository and tracking set-up |
| M1 — Extract + Load | Docker infrastructure, CI, `raw`/`audit` schemas, 4 extractor modules covering 5 sources (both OECD dataflows share one module), loader, CLI |
| M2 — SQL transform | SQL `staging`, `mart` and `checks` layers, SQL tests |
| M3 — Dashboard (V1) | Provisioned Grafana dashboard, end-to-end test, first real load |
| M4 — Wrap-up | README with screenshots, cron, review, risk review |

### Roles

- **Richard, project lead:** decides and approves. Approval is required for structural decisions, public actions and each milestone close.
- **An AI coding assistant:** proposes and implements.

### Quality gates

- Independent review of each task (specification compliance first, then code quality).
- Acceptance check of each issue, with command outputs as evidence.
- Documentation consistency check before any commit touching documents or configuration.
- Retroactive review and acceptance check at each milestone close, followed by the project lead's approval.

## 8. Success criteria

1. `make up && make etl` loads the history from **2015-01-01** without error.
2. Re-running `make etl` leaves the row counts of `raw.*` and `mart.*` unchanged (**idempotence**).
3. The dashboard shows, for the selected countries: the exchange rate, inflation, the inflation gap with the euro area, the currency depreciation, the PPP gap, and the pipeline health.
4. `make test`: all tests pass.
5. `PROGRESS.md`: every task is done, with its commit and its verification evidence.

## 9. Version history

| Version | Date | Change | Status |
|---|---|---|---|
| 1.0 | 2026-10-02 | First version, derived from the design specification | Draft — pending project lead approval at the M0 milestone review |
