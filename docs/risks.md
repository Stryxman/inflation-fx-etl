# Risk register

| ID | Risk | Probability | Impact | Planned mitigation | Status |
|---|---|---|---|---|---|
| R1 | An API changes format or key (as the OECD and the ECB did in 2025-12) | High | High | One source per module; tests on fixtures; each source is isolated; `audit.etl_runs` and a freshness check | Open |
| R2 | Monthly data missing for some countries | Materialised, then resolved | Medium | Task 3 found the cause was an API migration (OECD COICOP 2018 dataflow, ECB HICP), not missing data. Mitigation: decision [D11](decisions.md) (monthly series from the right dataflows, dormant annual World Bank fallback marked `is_fallback`) and a CPI freshness check (latest period of each monthly series no older than 3 months before the current month, per country). Residual gap: USA 2025-10 is missing at the source and kept empty, without interpolation | Mitigated by D11; freshness alert to be implemented (M2) |
| R3 | Revisions of past series | Medium | Low | 10-day overlap window and UPSERT | Open |
| R4 | Docker missing or misconfigured on the machine | Medium | High | Prerequisite documented; `make up` checks the healthcheck | Open |
| R5 | Scope drift (crypto, other countries) | Medium | Medium | Out-of-scope list written in the project charter; checked by the acceptance agent (`qa-verifier`) | Open |
| R6 | Misreading of an indicator (depreciation direction, PPP base) | Medium | High | Formulas in the project charter; SQL tests with exact values | Open |
| R7 | API rate limits are hit | Low | Medium | Incremental mode; retries with increasing delay | Open |
| R8 | Credentials leak (`.env`) | Low | High | `.env` ignored by git; only `.env.example` is versioned | Open |
