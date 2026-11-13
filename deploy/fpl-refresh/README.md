# Validated FPL refresh

The historical pipeline has **not** been deployed or backfilled into production.
An isolated live backfill, BigQuery dbt build and local API smoke test have passed;
see `HISTORY_VALIDATION.md`. Earlier production deployment records are in `VALIDATION.md`.

The existing scheduler remains `FPL-bigquery-ingestion`, `0 */6 * * *` in
`America/Vancouver`. Do not create another scheduler. The workflow now:

1. Acquires the pre-created BigQuery `refresh_control` singleton in a transaction.
2. Runs ingestion with the workflow execution UUID as `FPL_RUN_ID`.
3. Runs the dbt/publication job after ingestion succeeds.
4. Releases ownership and logs success only after publication/verified no-change.

Both jobs verify ownership and transactionally claim their stage using the
Cloud Run execution ID. Duplicate submissions within one workflow are fenced
before raw writes or publication; they cannot both execute the same stage.
Cloud Run task count/parallelism do not themselves prevent overlapping executions. A second workflow fails acquisition without
starting either job. Query job IDs make connector resubmissions identifiable.

## Failure handling

Failed, cancelled, or ambiguous executions **retain their lock**. This is a
conservative extension of the plan: a connector timeout does not prove a job
stopped, so automatic unlocking could allow concurrent raw writes. Inspect the
workflow error, both job executions, and Cloud Logging using the same run ID.
Raw tables can be partially updated, but published-mode API data stays on its
last validated snapshot. A failed run can also have merged history corrections;
the next successful run detects those changes even if its own merge changes zero
rows. No automatic rollback or blind Cloud Run submission retry occurs.

Before manually releasing a lock, verify its owner workflow, both jobs, and
**all BigQuery jobs labelled `fpl_run=<owner UUID>`** are terminal. A timed-out
Cloud Run execution does not prove its submitted query/load/copy stopped. Python
jobs log BigQuery job IDs; dbt and workflow queries carry the same run label.
Pause the scheduler during recovery. Inspect:

```sh
bq query --project_id=fpl-optimizer-511321 --location=US --use_legacy_sql=false \
  'SELECT * FROM `fpl-optimizer-511321.fpl_raw.refresh_control`'
gcloud workflows executions list fpl-refresh --project=fpl-optimizer-511321 --location=us-central1
gcloud run jobs executions list --job=fpl-bigquery-ingestion --project=fpl-optimizer-511321 --region=us-central1
gcloud run jobs executions list --job=fpl-dbt-build --project=fpl-optimizer-511321 --region=us-central1
```

An operator with project job-inspection access can check unfinished warehouse
work (the location qualifier is `region-us` for these US datasets):

```sh
bq query --project_id=fpl-optimizer-511321 --location=US --use_legacy_sql=false \
  --parameter='owner:STRING:REPLACE_WITH_OWNER_UUID' \
  "SELECT job_id, job_type, state FROM \`fpl-optimizer-511321.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT\`
   WHERE creation_time>TIMESTAMP_SUB(CURRENT_TIMESTAMP(),INTERVAL 7 DAY) AND state!='DONE'
     AND EXISTS(SELECT 1 FROM UNNEST(labels) WHERE key='fpl_run' AND value=@owner)"
```

Wait for pending jobs, or cancel those that support cancellation and confirm
terminal state. Only after no execution/job can still write, release ownership:

```sh
bq query --project_id=fpl-optimizer-511321 --location=US --use_legacy_sql=false \
  --parameter='owner:STRING:REPLACE_WITH_VERIFIED_TERMINAL_EXECUTION_UUID' \
  "UPDATE \`fpl-optimizer-511321.fpl_raw.refresh_control\`
   SET owner=NULL, acquired_at=NULL WHERE lock_id='refresh' AND owner=@owner"
```

Start a **new workflow execution**, not either job directly. Normal ingestion and
dbt jobs reject missing run IDs. Restrict job invocation to the workflow identity;
remove the old ingestion identity's self-invoker grant during migration. Owners
with administrative permissions must also follow this protocol.

## Safe initial rollout — operator actions, not performed here

1. Validate in isolated raw/build/published datasets first, all in `US`, using the
   same five existing catalog schemas and deterministic API inputs. Override
   `RAW_DATASET`, `DATASET_ID` (build), `PUBLISHED_DATASET`, and corresponding job
   environments. Test overlapping workflow starts and deliberately failed
   ingestion/tests. A SQL parse or local DuckDB run cannot replace these checks.
2. Pause the production scheduler and verify workflow/jobs are idle. Keep the
   current images/workflow revision and published data for rollback.
3. Run `bash deploy/bigquery-ingestion/setup.sh`. This explicitly provisions four
   raw history/control tables without expiration and scopes ingestion write
   access to the raw dataset before removing its broad project grant. It uses
   `.venv-web/bin/python` by default; `PYTHON` can select another prepared runtime.
4. Run `bash deploy/dbt-build/setup.sh`. This creates `fpl_build` in the raw
   dataset's location, grants dbt read access to raw, write access to build and
   published datasets, and table-level manifest update access.
5. Deploy both new job images with their existing deployment scripts. Set
   `FPL_SEASON=2026-27` consistently. For the first backfill, choose
   `TASK_TIMEOUT=3600s` for ingestion; measure its runtime before reducing it to
   the normal 600-second default. The workflow waits up to 3,900 seconds for
   ingestion and 1,500 seconds for dbt. Do not raise the dbt task timeout beyond
   its connector timeout without updating both.
6. Run `bash deploy/fpl-refresh/setup.sh`, then `bash deploy/fpl-refresh/deploy.sh`.
   Setup adds job-scoped `run.jobs.runWithOverrides`, project BigQuery Job User,
   and table-scoped control access for the workflow identity. Existing invoker
   and operation-poll permissions remain. Remove ingestion's legacy self-invoker
   binding on the ingestion job after verifying the workflow grants.
7. Run `gcloud workflows run fpl-refresh --project=fpl-optimizer-511321
   --location=us-central1` as one shell command. First execution backfills every
   current player. Confirm complete manifests, warning classifications, passing
   critical tests, archived candidates, and the published snapshot.
8. Enable `FPL_USE_PUBLISHED_SNAPSHOT=true` on the local/backend or a subsequently
   deployed web service. Published mode reads one table, never silently falls
   back to raw, and needs no raw dataset access. Grant a web service account
   BigQuery Job User and table-level Data Viewer on
   `fpl_analytics.mart_recommendation_snapshot` before removing old raw grants.
9. Smoke-test catalog/import/replacements/both optimiser modes and version-409
   recovery. Resume the existing scheduler; verify its next complete execution.
   `schedule.sh` is needed only if the scheduler must be retargeted; it preserves
   the actual existing cadence/timezone and does not force a run.

All setup/deploy scripts are explicit operator operations. No script is executed
by importing Python modules. Changing environment variables never changes cloud
resources until an operator runs the appropriate deployment command.

## Checkpoints, scheduling and costs

Bootstrap/fixtures still refresh together every six hours. History selects new
players, changed team assignments, finished/changed fixtures, current and
historical club participants, daily recent-two-completed-GW checks, and a weekly
full reconciliation. The first run is a full sweep. FPL element-summary always
returns the player's full current season; only request selection and BigQuery
merges are incremental. Removed players are preserved in history but are not
requested after disappearing from the current catalog.

Daily/weekly checks refresh coverage metadata and produce a tested candidate,
even when metric payloads are unchanged. Runs with no catalog, history, or
collection-coverage changes skip dbt and atomically advance the serving check
timestamp without changing publication ID. All five raw loads and manifest/run
coherence must still pass. A previous unpublished manifest forces a rebuild.

No separate recurring history job/scheduler or new orchestration service is
needed. Requests are bounded to two concurrent workers with retries. History
loads/checkpoints are batched. Python control queries and workflow lock queries
have a 100 MB billing cap; the web reader retains its existing query cap. BigQuery
minimum billing and other project usage still apply. Measure job duration and
processed bytes before increasing cadence or adding partitioning.

## Monitoring

Cloud Logging receives run IDs, selection counts, changed history rows, dbt test
output, failure stage, and workflow success/failure. dbt's local artifacts are
inspected before publication and remain ephemeral; forward evaluation snapshots
are persistent BigQuery tables. `pipeline_runs` records collection and
publication success separately. API health remains a process-only check.

Optional Cloud Monitoring configurations are in `monitoring/`. Attach an existing
notification channel when provisioning the failure and 12-hour success-absence
policies; no recipient is invented. Create the log-based `fpl_refresh_success`
metric first, then obtain one successful observation before evaluating absence.
Adjust the workflow-ID filter if the workflow name is overridden. No monitoring
resources are created automatically.

## Rollback

Pause scheduling and verify jobs are idle. Published snapshot replacement is one
atomic BigQuery copy; `_previous` holds the prior snapshot. Restore that table
with an atomic copy if required, and roll back the web/job images and workflow
revision together. Keep published mode enabled when restoring a published
snapshot; legacy mode reads independently refreshed raw tables.

Before resuming a corrected pipeline after data rollback, set
`FPL_FORCE_BUILD=true` on the dbt job for one workflow run so an unchanged-input
heartbeat cannot keep the intentionally restored older rankings. Remove the
flag afterward. Restoring API data does not roll back raw history corrections.
