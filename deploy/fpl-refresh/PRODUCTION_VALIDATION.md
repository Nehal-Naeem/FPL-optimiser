# Production rollout — November 13, 2026

Public application: https://fpl-web-381011398272.us-central1.run.app

## Data and deployment

Production uses `fpl_raw` for inputs/control, `fpl_build` for candidate models and
`fpl_analytics` for validated publication and immutable forecast archives. The
three `_localtest` datasets and their archives were retained. Sample Jaffle Shop
seeds are disabled; their six tables and the empty `fpl_analytics_raw` dataset
were removed individually after dependency, backup and typed CSV parity checks.
No recursive dataset deletion was used.

The five production raw API tables and raw dataset default no longer expire.
Build objects retain a seven-day default; persistent history/control tables and
published/archive copies explicitly have no expiration.

Images in the existing `us-central1/fpl-jobs` Artifact Registry repository:

- Ingestion: `fpl-bigquery-ingestion:20261113205038`
- dbt: `fpl-dbt-build:20261113205120`
- Web: `fpl-web:20261113205706`

Cloud Build IDs: `4165b31a-be74-42a9-877c-13e55608984b`,
`b46ee690-8105-40f9-9404-d9023657ab81`,
`7f2b16bc-cb1a-4984-81f2-e873e25d7289` (all successful).
Workflow revision: `000003-64f`. Web revision: `fpl-web-00001-mgd`.

The web identity has project BigQuery Job User and table-only Data Viewer on
`fpl_analytics.mart_recommendation_snapshot`; it has no raw/build dataset grant.
The service explicitly enables published mode, with 1 CPU, 1 GiB, concurrency 4,
0 minimum instances, 3 maximum instances and 120-second timeout. Public access
was granted only after authenticated API and desktop/mobile checks passed.

## Validation evidence

- Python/backend/SQL/evaluation: 89 tests pass.
- Browser regressions: 29 pass; one mouse-hover test intentionally skipped on mobile.
- Frontend TypeScript/Vite build and all three Cloud Build images pass.
- Production dbt: 20 models, 117 data tests, two unit tests; **PASS=139 WARN=0
  ERROR=0 SKIP=0**. Source freshness also passed before build.
- First backfill fetched 672 players and merged 6,562 unique fixture observations.
  Serving data has 672 unique players, 389 scored, all with complete recent
  history and five projection weeks (GW 11–15 at deployment).
- The first workflow `4d790b6f-b1d9-4f2b-a2ce-3109c984e370` published validated
  data and released its lock, then failed its final success-log call because the
  workflow identity lacked `logging.logEntries.create`. The identity received
  `roles/logging.logWriter`; provisioning now includes that role.
- Scheduler-triggered retry `78f566e5-4748-4e9c-964d-3a76434f7f26` fully succeeded,
  published again and released the lock. This also exercised subsequent table
  publication after granting the web identity table-level read access.
- Private and unauthenticated public API checks passed: health, HTML, 672-player
  catalog, real public team import, replacements, both ideal optimisers, zero-
  transfer replay, bank conservation, legal weekly XIs/captaincy and version-409.
- Deployed desktop/mobile Chrome checks passed: 11 weekly starters, 15-player
  rotation grid, bench order, projection popovers, no viewport overflow and no
  JavaScript errors. Evidence screenshots are in the git-ignored backup directory.
- On the 1-CPU service, points mode returns a legal FEASIBLE result within its
  10-second solver budget. The UI explicitly reports unproved optimality and
  unfinished secondary tie-breaks. Projections remain experimental/uncalibrated.

## Recovery assets

Local backup directory:
`logs/local-refresh/deployment-20261113T204736Z/`

It contains 77 original backup/configuration files with SHA-256 checksums,
sample CSVs, table schemas/NDJSON, raw/evaluation data, view SQL, original job and
workflow configurations, scheduler settings and original IAM bindings. Additional
validation JSON and screenshots are stored alongside them. Logs are excluded
from Git and Docker upload; only app source files were uploaded for the web build.

To recover deleted sample tables, recreate `fpl_analytics_raw` in US, then use
`bq load --source_format=NEWLINE_DELIMITED_JSON` with each saved `.ndjson` and
`.schema.json` pair. Keep seeds disabled unless intentionally restoring their
build behavior.

For pipeline rollback, pause scheduling and verify jobs are idle; restore only
the affected configuration/bindings from backup, not the whole project IAM
policy. Restore the saved compatibility data/views as necessary. Keep the web
service private if the restored pipeline cannot serve the validated snapshot.
After successful publication, the `_previous` serving table and immutable UUID
archives provide atomic data rollback; use the existing recovery guide.

The recurring schedule remains `0 */6 * * *` in `America/Vancouver`. Validation
runs were submitted through Scheduler; they are not evidence of a later natural
cron tick. The final post-cleanup execution/result is recorded below.

## Final post-cleanup check

Scheduler-triggered execution `716617bf-2370-41a6-8c43-6b400c0afda4` succeeded
after dataset removal (ended `2026-11-13T23:10:49.130853771Z`). It published snapshot
`716617bf-2370-41a6-8c43-6b400c0afda4`, passed all 139 dbt resources with no
warnings/errors/skips, and released the refresh lock. The sample dataset remained
absent. Final datasets are `fpl_raw`, `fpl_build`, `fpl_analytics`,
`fpl_raw_localtest`, `fpl_build_localtest`, `fpl_analytics_localtest`.

The scheduler is ENABLED with its original cron/timezone; the next natural tick
is reported as `2026-11-14T01:00:02.567152Z`. That future tick has not yet been
observed. No local development server was left running.
