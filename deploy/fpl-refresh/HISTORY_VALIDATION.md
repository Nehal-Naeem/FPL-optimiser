# Historical pipeline implementation validation

Validated locally on November 13, 2026. No production data, IAM, scheduler,
workflow, Cloud Run image, or service was changed. No historical API backfill was
performed. The earlier `VALIDATION.md` records the pre-migration deployment.

## Completed checks

- 65 backend/ingestion Python tests passed in the existing web environment.
  Coverage includes original optimiser constraints/objective and API behaviours,
  published snapshot coherence, successful-check freshness, descriptive squad
  diagnostics, typed history, retry/selection policy, fail-before-write handling,
  raw-load/checkpoint failures, publication gates and rollback-copy ordering,
  failed-run correction recovery, and duplicate-stage rejection.
- 29 ingestion tests also passed on Python 3.12.16 with the existing production
  BigQuery client dependency set.
- Seven local SQL regression tests passed on Python 3.12 using actual model and
  MERGE SQL translated from BigQuery to DuckDB. Scenarios include negative
  points, missed appearances, unknown blank/membership context, double GWs,
  completed cutoffs, early-season denominators, optional xG, zero minutes,
  incomplete collection, season isolation, corrections/rescheduling, idempotent
  merges, full candidate graph/fixture serialization, and a deliberately
  corrupted aggregate detected by the reconciliation test.
- dbt Core 1.10.15 / BigQuery adapter 1.10.2 parsed the complete project on Python
  3.12: 15 models, 103 data tests, two native unit tests and one comparison
  analysis. The six starter seeds remain excluded from runtime builds.
- Frontend TypeScript checking and Vite production build passed.
- 27 Playwright desktop/mobile tests passed; one desktop hover test is
  intentionally skipped on mobile. New checks cover measured/null history,
  incomplete coverage, low minutes, allocation and objective-limit explanations.
  The longer popover initially covered its trigger on mobile; placement now
  constrains panel height to available space and the full suite passed.
- Deployment/model YAML parsed, deployment shell scripts passed `bash -n`, Python
  compilation passed and `git diff --check` passed.

The existing web test interpreter is Python 3.9.6 and emits Python/LibreSSL support
warnings. Production targets Python 3.12. Temporary validation environments were
used instead of replacing either existing project environment. No production
runtime dependency or scoring weight was added/changed.

## Remaining rollout gates

Docker is unavailable locally; container images were not built. dbt parsing and
DuckDB translations do not prove BigQuery adapter execution. The 103 native
checks and two dbt unit tests have not been executed in BigQuery. Cloud Workflows
compilation, IAM permissions, connector behaviour, transactional concurrency,
backfill duration/memory, monitoring policies and atomic publication require
isolated cloud validation before activating the new images on production.

Follow `README.md` here for migration, deliberate failure/overlap scenarios,
first-backfill timeout, backend migration switch, and recovery. In particular,
keep scheduling paused while replacing the jobs/workflow together and enable
published backend mode only after a validated snapshot is available.

## Isolated live backfill and local app — November 13, 2026

The live pipeline has now completed using existing user ADC and three isolated
US BigQuery datasets: `fpl_raw_localtest`, `fpl_build_localtest`, and
`fpl_analytics_localtest`. Production tables, scheduled jobs, workflow definition,
IAM and cloud services were not changed. A local server was started separately.

- Run/publication ID: `4efb7135-e96a-4511-958a-d9e26347e407`.
- Fetched histories for all 672 current players; merged 6,562 current-season
  player-fixture records. Catalog/source loads and checkpoint reconciliation passed.
- All five source-freshness checks passed in BigQuery.
- Native dbt build: **PASS=120 WARN=0 ERROR=0 SKIP=0**: 15 models, 103 data tests,
  and two unit tests. This supersedes the earlier “not executed in BigQuery” gate
  for these models/tests, while cloud-container/IAM/Workflows validation remains.
- BigQuery execution exposed test SQL that used unsupported `HAVING` and
  `WHERE`-without-`FROM` forms. Those queries now use explicit aggregate/anchor
  relations. Fixture arrays now aggregate by club before joining the serving
  model, avoiding unsupported externally correlated subqueries. These fixes also
  pass the local SQL regressions.
- Failed attempts retained the isolated lock and blocked publication. The local
  resume command verified terminal warehouse jobs before resetting only the
  failed build claim; it reused the successful backfill. The final validated
  publication, manifest update, snapshot archives and lock release succeeded.
- Local API smoke tests returned HTTP 200 for health, catalog, optimisation and
  frontend HTML. Published mode returned 672 unique players, 389 scored, all 672
  with complete recent context through completed GW 10, and `stale=false`.
- A real £100m ideal optimisation returned `OPTIMAL`, 15 players, £89.8m spend,
  and £10.2m remaining. Position quotas, uniqueness, budget and club limits passed;
  the response included historical features and six descriptive diagnostics.
- The existing backend/ingestion regression suite now has 66 passing tests,
  including the isolated-local-stage guard. Seven local SQL regressions passed.

The built React frontend and API are served together at
`http://127.0.0.1:8000`. Restart with `bash scripts/serve_local.sh`; refresh the real
test data using the prepared Python 3.12 dbt environment and
`python scripts/local_refresh.py`. Run logs and dbt artifacts are retained under
`logs/local-refresh/<run UUID>/` (git-ignored).

## Experimental points planner — November 13, 2026

- Validated publication `2fe33eb5-c5fd-4166-ace2-bf89034ccafd` in the same three
  isolated `_localtest` datasets. Incremental ingestion found no player histories
  needing refresh and reused the 6,562 stored records; current catalog/fixtures
  were rechecked. Production schedules, services and IAM remain unchanged.
- Native source freshness: five passes. Native dbt build: **PASS=139 WARN=0
  ERROR=0 SKIP=0** (20 models, 117 data tests, two unit tests). All 672 players
  have five projection weeks, GW 11–15; fixture/GW/component checks passed.
- Both new projection marts and the serving snapshot were archived before
  publication. The read-only prospective evaluation SQL passed BigQuery dry-run
  validation (568,374 estimated bytes). Future accuracy has not been measured.
- Real-data ideal points mode: primary `OPTIMAL`, 308.55 experimental XI + captain
  points across five weeks, £99.5m market value, £0.5m remaining, about 9.7 seconds.
  Secondary tie-breaks were incomplete and are explicitly flagged. Each week's
  stress test covered 11 single and 55 double absences under the stated reserve
  appearance heuristic. These are not calibrated coverage probabilities.
- Legacy ideal mode remained `OPTIMAL`, £89.8m spend/£10.2m remaining.
  New-mode zero-transfer replay retained the full squad and bank, returned the
  identical baseline total, and completed all tie-breaks in about 0.62 seconds.
- Python: 47 backend tests and 42 SQL/ingestion/evaluation tests pass. Browser:
  29 desktop/mobile tests pass; one mouse-hover test intentionally skipped on
  mobile. TypeScript/Vite build passes. API gzip reduces the larger nested
  projection catalog without adding dependencies or queries.

See [projection methodology](../../docs/POINTS_PLANNER.md) before interpreting the
experimental points. The local server uses the published test snapshot; no cloud
web deployment was performed.


## Production status supersedes earlier deployment gates

The full pipeline and public webapp are now deployed. See
[production rollout and verification](PRODUCTION_VALIDATION.md) for native cloud
checks, Scheduler validation, the sample-dataset cleanup and recovery assets.
Earlier entries above describe the environment as it existed at those stages.
