# Decision log

All decisions below were taken or approved by Richard (project lead) on 2026-10-02. Justifications are product reasons.

| ID | Date | Topic | Decision | Status |
|---|---|---|---|---|
| D1 | 2026-10-02 | Tracked subject | Inflation and exchange rates, crossed | Approved 2026-10-02 |
| D2 | 2026-10-02 | Crypto | Out of V1, planned for V2 as a third source | Approved 2026-10-02 |
| D3 | 2026-10-02 | Database | PostgreSQL 17 under Docker | Approved 2026-10-02 |
| D4 | 2026-10-02 | Presentation | Grafana, dashboards provisioned as JSON | Approved 2026-10-02 |
| D5 | 2026-10-02 | Countries | 4 developed (USA, GBR, JPN, CHE) and 4 emerging (TUR, BRA, IND, ZAF) against the euro | Approved 2026-10-02 |
| D6 | 2026-10-02 | Method | Raw loading, then transformation in SQL inside the database (ELT): `raw` -> `staging` -> `mart` | Approved 2026-10-02 |
| D7 | 2026-10-02 | Tracking | Specialist sub-agents, `PROGRESS.md`, GitHub issues, milestones and board | Approved 2026-10-02 |
| D8 | 2026-10-02 | Approval | The project lead approves structural decisions, public actions and each milestone close | Approved 2026-10-02 |
| D9 | 2026-10-02 | Pace | Milestones chained with no target date | Approved 2026-10-02 |
| D10 | 2026-10-02 | Repository | Public repository `inflation-fx-etl` | Approved 2026-10-02 |
| D11 | 2026-10-02 | Inflation data | Monthly: OECD (legacy dataflow + new COICOP 2018 dataflow) and ECB HICP; annual World Bank fallback coded but dormant; freshness alert; USA 2025-10 left empty | Approved 2026-10-02 |
| D12 | 2026-10-02 | Language | All public content in English | Approved 2026-10-02 |
| D13 | 2026-10-02 | Progress tracking | The orchestrator updates the log; the tracking agent only at milestone close (measured cost) | Approved 2026-10-02 |

## D1 — Tracked subject

**Context.** The project needs a single, clear question that gives the data a purpose and shows how several sources combine.

**Options considered.**
- Exchange rates only.
- Inflation only.
- Both, crossed.

**Decision.** Inflation and exchange rates, crossed.

**Rationale.** Neither series answers a question on its own. Crossing them answers one that matters for anyone holding foreign currencies: does a currency depreciate when its country's inflation exceeds that of the euro area? It also requires combining sources with different formats and frequencies.

## D2 — Crypto

**Context.** Crypto-currencies could be added as another asset class to compare against inflation.

**Options considered.**
- Include crypto in V1.
- Add it later, as a third source.

**Decision.** Out of V1; planned for V2 as a third source.

**Rationale.** Crypto has no national inflation counterpart, so it does not fit the tracked question. Keeping it out of V1 keeps the scope small enough to deliver a complete, tested pipeline first.

## D3 — Database

**Context.** The pipeline needs a store for raw data and SQL-built indicators, usable locally by the dashboard.

**Options considered.**
- DuckDB.
- SQLite.
- PostgreSQL in Docker.

**Decision.** PostgreSQL 17 under Docker.

**Rationale.** PostgreSQL is a multi-user server database that Grafana reads natively, supports schemas (`raw`, `staging`, `mart`, `audit`), materialised views and transactional layers, and is what most production analytical stacks use. Docker makes the set-up reproducible with one command.

## D4 — Presentation

**Context.** The analyst needs a dynamic dashboard with filters, refreshed from the database.

**Options considered.**
- Streamlit + Plotly.
- Static HTML + Plotly.js.
- Grafana.
- Metabase.

**Decision.** Grafana, with dashboards provisioned as JSON.

**Rationale.** Grafana connects directly to PostgreSQL, offers variables, time-series panels and auto-refresh out of the box, and its datasource and dashboards can be provisioned from versioned files, so a fresh start gives the same dashboard without manual set-up. It also suits the pipeline-health panel.

## D5 — Countries

**Context.** The question compares emerging-market and developed-market currencies, so the sample must contain both.

**Options considered.**
- Mixed set of 8 countries (4 developed, 4 emerging).
- Emerging countries only.
- A configuration-only list with no fixed default.

**Decision.** 4 developed (USA, GBR, JPN, CHE) and 4 emerging (TUR, BRA, IND, ZAF) against the euro.

**Rationale.** A mixed set lets the analyst compare groups and shows the effect of high inflation (for example TUR) against stable references. Eight countries keep the dashboard readable and the data volume small. The list lives in `config/countries.yaml`, so it can be changed without code.

## D6 — Method

**Context.** Sources are heterogeneous and can be revised; the pipeline must be traceable and re-runnable.

**Options considered.**
- Classic ETL: transform in Python before loading; less SQL, but raw data is lost and transformations cannot be replayed from the database.
- ELT: load raw data, then transform in SQL inside the database; full traceability and replayable layers, at the cost of a larger database.

**Decision.** Load raw data first, then transform it in SQL inside the database (ELT): `raw` -> `staging` -> `mart`.

**Rationale.** Keeping data as received makes every indicator traceable to its source and allows transformations to be corrected and replayed without re-downloading. SQL layers are versioned, testable with exact expected values, and visible to the analyst.

## D7 — Tracking

**Context.** The project needs visible progress and a clear division of work.

**Options considered.**
- Specialist agents plus a progress log file (`PROGRESS.md`).
- Specialist agents plus a shared web tracking page.
- Specialist agents and git history only, without a dedicated log.

**Decision.** Specialist sub-agents, `PROGRESS.md`, GitHub issues, milestones and board.

**Rationale.** Specialised roles keep each task focused and independently reviewable. A progress log, issues and a board make the state of the project readable by anyone at any time.

## D8 — Approval

**Context.** The project lead needs control over what matters without approving every change.

**Options considered.**
- Approval of structural decisions, public actions and milestone closes.
- Approval of every pull request: more control, many more interruptions.

**Decision.** The project lead approves structural decisions, public actions and each milestone close, not each pull request.

**Rationale.** Approving only these points keeps the pace high while keeping control where a mistake is hard to undo (public actions) or shapes the project (structural decisions, milestone close).

## D9 — Pace

**Context.** No external deadline applies to the project.

**Options considered.**
- One milestone per day with target dates.
- Chained milestones with no target date.
- A slower pace of one milestone every two to three days.

**Decision.** Milestones are chained with no target date.

**Rationale.** Progress is paced by quality gates and milestone approvals rather than by dates, which avoids trading verification for speed.

## D10 — Repository

**Context.** The project is meant to be published as an open repository.

**Options considered.**
- Public GitHub repository with milestones, issues and a board from the start.
- Local repository first, published later; progress tracked only in `PROGRESS.md`.

**Decision.** Public repository named `inflation-fx-etl`, with milestones M0–M4, labels and a public board ([project board](https://github.com/users/Stryxman/projects/2)). Name and creation approved by the project lead on 2026-10-02, before the repository was created.

**Rationale.** The name states what the project does. Creating a public resource is a public action, so it is gated by D8.

## D11 — Inflation data

**Context.** Verification of the sources (2026-10-02) showed that the apparent gaps in monthly inflation data came from API migrations, not from missing data: the OECD moved several countries from its legacy dataflow to a COICOP 2018 dataflow, and the ECB replaced its frozen `ICP` dataset with `HICP`. The USA also has one missing observation (2025-10).

**Options considered.**
- Monthly data with a dormant World Bank annual fallback.
- Monthly data without any fallback.
- World Bank annual data only.

**Decision.** Monthly data from the OECD (legacy dataflow for USA, GBR, BRA, IND; COICOP 2018 dataflow for JPN, CHE, TUR, ZAF) and from the ECB HICP dataset (key provider `4D0`, replacing the frozen `ICP`) for the euro area. The annual World Bank fallback is coded but dormant. USA 2025-10 is left empty, with no interpolation. A freshness check (latest period of each monthly series no older than 3 months before the current month, per country) warns when a series stops advancing.

**Rationale.** Monthly data is required to compare inflation with monthly exchange-rate moves; annual data would hide most of the signal. The fallback keeps the pipeline able to display a country if its monthly series ever disappears, at no cost while dormant. Leaving the USA gap empty avoids inventing data. The freshness alert makes the next API migration visible instead of silent.

## D12 — Language

**Context.** The repository is public and its audience is not limited to French speakers.

**Options considered.**
- English everywhere.
- French documentation with English code.
- French everywhere.

**Decision.** All public content in English: code, documents, README, `PROGRESS.md`, commits, issues and board.

**Rationale.** A single language across code, documents and tracking avoids mixed vocabulary and makes the project readable by the widest audience of analysts and contributors.

## D13 — Progress tracking

**Context.** `PROGRESS.md` must be updated after each task. A dedicated tracking agent was measured at about 44k tokens per update.

**Options considered.**
- The orchestrator updates the log; the tracking agent only intervenes at milestone close.
- Always use the tracking agent.

**Decision.** The orchestrator makes the routine updates of `PROGRESS.md`; the tracking agent is used only at milestone close.

**Rationale.** The log stays current at a small fraction of the cost, and the milestone-close pass still gives a thorough, independent consolidation where it adds the most value.
