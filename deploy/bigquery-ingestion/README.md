# FPL BigQuery ingestion job

The repository job now captures current catalogs and current-season fixture
history. See [rollout and recovery](../fpl-refresh/README.md) before deploying;
the old deployed image does not gain this behaviour automatically. A complete
isolated live backfill has passed; see `../fpl-refresh/HISTORY_VALIDATION.md`.

`scripts/bigquery_ingestion.py` is import-safe. It validates bootstrap and fixtures,
checks configured season dates, fetches all selected player histories, then merges
history and replaces players/gameweeks/positions/teams/fixtures. It waits for load
completion and reconciles row counts/run IDs before recording a successful run.
Raw replacements are individually atomic; validated serving snapshots protect the
API from partial refreshes. Any required API failure blocks checkpoints and dbt.

History comes from `element-summary/{id}/`, not gameweek live aggregates. The
latter cannot supply all underlying metrics per fixture in double gameweeks.
Each element-summary call returns full season history; request selection reduces
calls, while payload hashes prevent unchanged canonical rows being rewritten.

Tables created by explicit `setup.sh`:

- `player_fixture_history`: `(season, player_id, fixture_id)`; typed counts,
  NUMERIC expected/ICT metrics, fixture context, payload hash, observation time,
  run ID. Signed points/BPS/transfer balances are valid. Optional metrics stay
  null. Corrections update existing natural keys; changed gameweeks do not create
  new fixture keys. Raw records are never automatically deleted.
- `player_history_checks`: successful checks, including genuinely empty
  histories, current club, daily/weekly cadence checkpoints. An empty history for
  a player with recorded season minutes is rejected.
- `pipeline_runs`: ingestion success, input hash, selection/change counts,
  fixture snapshot, build requirement, and publication timestamp.
- `refresh_control`: one pre-created transactional ownership row.

These tables explicitly have no expiration, overriding the raw dataset's 60-day
default. Staging tables expire after one day. Retain older seasons without joining
season-scoped IDs to today's dimensions; a detected API rollover fails closed.

The runtime uses requests sessions per worker, two workers, connect/read timeouts,
up to four attempts for timeouts/429/5xx, Retry-After support and jittered backoff.
The weekly full reconciliation catches older corrections and imperfect targeted
coverage. HTTP-date/delta Retry-After waits are bounded at 120 seconds per retry;
longer throttling eventually fails the run rather than waiting indefinitely.

Configuration: `GOOGLE_CLOUD_PROJECT`, `BIGQUERY_DATASET` (or `FPL_RAW_DATASET`),
`BIGQUERY_LOCATION`, `FPL_SEASON`, and workflow-supplied `FPL_RUN_ID`. Use the existing
`fpl-ingestion` attached identity; no API secret or service-account key is needed.

`setup.sh` scopes ingestion Data Editor to raw and removes the previous project
Data Editor grant. Run it only in the reviewed rollout window. `deploy.sh` builds
an allowlisted context and deploys without executing the job; `TASK_TIMEOUT`
overrides its normal 600-second timeout. First backfill runs through the workflow,
not direct job execution, so it shares the global lock and publication checks.
