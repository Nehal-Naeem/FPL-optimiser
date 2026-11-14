# Candidate dbt build and validated publication

`fpl-dbt-build` retains its separate Cloud Run identity/job. Its Python entrypoint
now checks workflow lock ownership and exactly one complete ingestion manifest,
including the run ID in every raw catalog table.

It runs source freshness, then `dbt build --exclude resource_type:seed` against
`fpl_build`. This includes all active model/data/unit tests. Critical failures, skipped resources, missing required model results, and
nonzero dbt exit statuses block publication. Warnings are logged and permitted.
Starter seeds stay excluded. dbt Core 1.10.15 and adapter 1.10.2 remain pinned.

On success it archives `mart_player_fixture_projection`,
`mart_player_gameweek_projection` and `mart_recommendation_snapshot` with the
workflow UUID suffix, preserves `_previous`, then atomically copies the serving
snapshot. Published/archive copies have expiration removed. No compatibility
ranking mart is written. Historical retired warehouse objects are retained.

The serving contract is version 2, with `projections_updated_at`. A missing
contract marker forces migration rebuild even if input payloads are unchanged.

Unchanged runs skip dbt and update the serving collection heartbeat. Actual
projections and publication ID stay unchanged; stale status uses the successful check
time. `FPL_FORCE_BUILD=true` forces a build, useful after a deliberate rollback.
A previous failed/unpublished run or failed-run history corrections force rebuild.

## Configuration and permissions

- `GOOGLE_CLOUD_PROJECT`: default `fpl-optimizer-511321`.
- `DBT_DATASET`: default **`fpl_build`**, must differ from raw and published.
- `FPL_RAW_DATASET`: default `fpl_raw`; source declarations use it.
- `FPL_ANALYTICS_DATASET`: default `fpl_analytics`.
- `BIGQUERY_LOCATION`: default `US`; all datasets must match.
- `FPL_SEASON`: default `2026-27`; match ingestion.
- `FPL_RUN_ID`: supplied by the workflow; direct runs without ownership fail.

`setup.sh` provisions the build dataset with a seven-day default expiration and
validates locations. It grants dbt project Job User, raw Data Viewer, build and
published Data Editor, plus table-level manifest updates. It does not grant dbt
ownership of the refresh lock. `deploy.sh` uploads explicit source/tests/scripts,
builds the image, and deploys without execution. Credentials use attached ADC.

See [rollout, scheduling and recovery](../fpl-refresh/README.md). Shell setup,
container validation, IAM tests, BigQuery adapter execution and concurrency/failure
injection remain required before production activation.
