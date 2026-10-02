# Data sources

Verification date: 2026-10-02. Tested window: from 2015-01.

## 1. Sources

| ID | Provider | Content | Format | Frequency | Licence / terms of use | URL |
|---|---|---|---|---|---|---|
| `ecb_fx` | ECB, EXR dataset | Units of foreign currency per 1 EUR (USD, GBP, JPY, CHF, TRY, BRL, INR, ZAR) | CSV | Daily, business days | Free reuse of ESCB public statistics, provided the source is cited ("Source: ECB statistics") and neither the statistics nor their metadata are altered ([reuse policy](https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html)) | `https://data-api.ecb.europa.eu/service/data/EXR/D.{currencies}.EUR.SP00.A` |
| `ecb_hicp` | ECB, HICP dataset (Eurostat data) | Euro-area inflation: annual rate `ANR`, index `INX` (base 2025 = 100) | CSV | Monthly | Same terms as above; free reuse does not cover third-party data without the producer's consent | `https://data-api.ecb.europa.eu/service/data/HICP/{key}` |
| `oecd_cpi` | OECD, `DSD_PRICES@DF_PRICES_ALL` (COICOP 1999) | CPI: annual rate `GY`, index `IX` | SDMX-CSV | Monthly, quarterly | CC BY 4.0 by default: free use, including commercial, citing "OECD (year), dataset name, URL (accessed on ...)" ([open by default policy](https://www.oecd.org/en/about/oecd-open-by-default-policy.html)). Detailed terms are on [the terms and conditions page](https://www.oecd.org/en/about/terms-conditions.html), which could not be read automatically on 2026-10-02 (HTTP 403) | `https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/{key}` |
| `oecd_cpi_c2018` | OECD, `DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL` (COICOP 2018) | Same measures as `oecd_cpi` | SDMX-CSV | Monthly | Same as `oecd_cpi` | `https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/{key}` |
| `worldbank` | World Bank, API v2 | Country metadata and annual inflation `FP.CPI.TOTL.ZG` | JSON | Annual | CC BY 4.0 by default for World Bank datasets: cite the source and indicate any modifications ([licences](https://datacatalog.worldbank.org/public-licenses)) | `https://api.worldbank.org/v2` |

Rate limit: the OECD API rejects bursts of requests (message "You have exceeded the number of requests currently permitted"); calls must be spaced a few seconds apart and retried with an increasing delay.

## 2. Coverage by territory

Monthly annual-rate series, measured from 2015-01. No World Bank fallback is needed.

| Territory | Source | Selected key (annual rate) | Index key | Freq. | Period covered | Fallback |
|---|---|---|---|---|---|---|
| USA | `oecd_cpi` | `USA.M.N.CPI.PA._T.N.GY` | `USA.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 (gap: 2025-10) | no |
| GBR | `oecd_cpi` | `GBR.M.N.CPI.PA._T.N.GY` | `GBR.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| JPN | `oecd_cpi_c2018` | `JPN.M.N.CPI.PA._T.N.GY` | `JPN.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| CHE | `oecd_cpi_c2018` | `CHE.M.N.CPI.PA._T.N.GY` | `CHE.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| TUR | `oecd_cpi_c2018` | `TUR.M.N.CPI.PA._T.N.GY` | `TUR.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| BRA | `oecd_cpi` | `BRA.M.N.CPI.PA._T.N.GY` | `BRA.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| IND | `oecd_cpi` | `IND.M.N.CPI.PA._T.N.GY` | `IND.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| ZAF | `oecd_cpi_c2018` | `ZAF.M.N.CPI.PA._T.N.GY` | `ZAF.M.N.CPI.IX._T.N._Z` | M | 2015-01 to 2026-08 | no |
| EA | `ecb_hicp` | `M.U2.N.000000.4D0.ANR` | `M.U2.N.000000.4D0.INX` | M | 2015-01 to 2026-09 (last point: flash estimate) | no |

`ecb_fx` exchange rates: all 8 currencies exist, with 3,008 observations each from 2015-01-02 to 2026-10-01, and no gaps between currencies.

World Bank (`FP.CPI.TOTL.ZG`, data updated on 2026-07-13): latest available year is 2025 for BRA, CHE, GBR, IND, JPN, TUR, ZAF; USA: 2024 (the 2025 value is null). This source remains available as a fallback, but no monthly series needs it.

## 3. Technical notes

**OECD key.** Dimension order: `REF_AREA.FREQ.METHODOLOGY.MEASURE.UNIT_MEASURE.EXPENDITURE.ADJUSTMENT.TRANSFORMATION`. Annual rate: `CPI.PA._T.N.GY`; index: `CPI.IX._T.N._Z` (base 2015 = 100 on all selected series). Methodology `N` (national) is used; `HICP` exists only for USA (until 2024-12), GBR, CHE and TUR and does not cover any period better than `N`.

**Two OECD dataflows.** The OECD publishes two dataflows for the CPI: COICOP 1999 (`DF_PRICES_ALL`) and COICOP 2018 (`DF_PRICES_C2018_ALL`). For some countries, series were stopped in the legacy dataflow and continued in the new one. Findings in the legacy dataflow (monthly, from 2015-01):

| Country | Last period, legacy dataflow | Last period, new dataflow |
|---|---|---|
| JPN | 2021-06 | 2026-08 |
| ZAF | 2025-01 (quarterly: 2024-Q4) | 2026-08 |
| CHE | 2025-12 | 2026-08 |
| TUR | 2025-12 | 2026-08 |
| USA, GBR, BRA, IND | 2026-08 | no records |

Probable cause: countries are gradually switching to the COICOP 2018 classification; each country is published in only one of the two dataflows for its recent period. The series in the new dataflow are complete from 2015-01 (140 monthly observations), so no concatenation across dataflows is needed. To watch: USA, GBR, BRA, IND may switch in turn; the freshness check must raise an alert if a series' last period stops advancing or moves backwards.

**Quarterly.** `Q` series exist for most countries (USA, GBR, IND, BRA up to 2026-Q2; CHE, TUR up to 2025-Q4; JPN up to 2021-Q2; ZAF up to 2024-Q4 for the annual rate) but are not used, since the monthly series is up to date everywhere.

**USA gap 2025-10.** The US CPI for October 2025 is missing from the source (one missing observation; monthly, and 2025-Q4 for the `Q` series). Probable cause: data collection not carried out during the October 2025 US federal government shutdown. The pipeline must accept this gap (null value, no interpolation); the annual rate for 2025-11 exists.

**ECB ICP frozen, HICP active.** The `ICP` dataset is frozen at 2025-12 for all areas (last modification observed: 2026-01-24), including `U2`, `I8`, `I9`. The `HICP` dataset replaces it, with a key of the same structure but provider `4D0` instead of `4`: `M.U2.N.000000.4D0.ANR` (the old key `...4.ANR` returns 404 in `HICP`). `U2` (euro area, changing composition, includes Bulgaria since 2026) covers 2015-01 to 2026-09. The areas `I9`, `I10`, `B0`, `B6` stop at 2026-08. The values match the old dataset over 2015-01 to 2025-12 up to rounding (6 differences of 0.1 point out of 132 months).

**Euro-area index.** The `INX` index of the `HICP` dataset is on a 2025 = 100 base, whereas the old `ICP` was on a 2015 base. OECD indices are on a 2015 base. Comparisons must rely on annual rates, or indices must be rebased before comparison.

**Flash estimate.** The last `U2` point (2026-09, 3.8%) has observation status `E` (estimated) and will be revised; the others are `A`. The UPSERT with an overlap window covers this revision.

**World Bank.** The USA annual value for 2025 is null; the other countries have 11 years (2015-2025).
