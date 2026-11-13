# Deployment validation

Validated November 11, 2026 in project `fpl-optimizer-511321`, region
`us-central1`, with both BigQuery datasets in `US`.

## Container and standalone job

- Cloud Build `2ebc5b88-59ab-449e-b9f0-a460cc010aaf` passed dependency installation,
  `pip check`, package installation, and `dbt parse` on Python 3.12/Linux.
- Tested versions: dbt Core `1.10.15`, BigQuery adapter `1.10.2`, and dbt-utils
  `1.4.1`. The complete Python dependency set is pinned in the deployment bundle.
- Standalone execution `fpl-dbt-build-h9sv9` succeeded as the non-root container
  user using its attached service-account identity.
- dbt reported `PASS=9 WARN=0 ERROR=0 SKIP=0`: eight views and one table were
  created in `fpl_analytics`; starter seeds were excluded. The evaluation table
  contained 389 rows. No model data tests are currently declared.

## Workflow ordering and failure handling

- Workflow execution `30c18577-93b4-44e9-a805-8fdb53950fef` succeeded.
- Ingestion execution `fpl-bigquery-ingestion-62d2l` completed at
  `2026-11-11T05:46:20.544601Z`.
- dbt execution `fpl-dbt-build-78qzd` was created afterward, at
  `2026-11-11T05:46:28.847280Z`, and completed successfully.
- An isolated test using the same workflow definition failed its first job.
  Execution `2c2d40e1-c439-4524-a1db-d30b396d01d5` failed at `ingest`, and the
  second test job had no executions, confirming it was skipped.
- Another isolated test passed its first job and failed its second.
  Execution `b3f55680-a7cd-4078-9fd6-e63889f7a979` failed at `build` as expected.
- Temporary test workflows and jobs were deleted after validation. Production
  job configuration was not changed to simulate errors.
- Final revision `000002-f9f`, execution
  `27e559ab-7265-4161-8c2e-1ef902197cab`, also succeeded and returned actual
  execution resource names from the connector's `response`:
  `fpl-bigquery-ingestion-q5h2p` and `fpl-dbt-build-x8dsk`.

## Repository checks

- All four new shell scripts passed `bash -n`.
- `git diff --check` passed, and relative documentation links resolve.
- The initial November 11 deployment created no Cloud Scheduler trigger. Global
  concurrency protection, source freshness policies, and new model data tests
  remain follow-up work.

## Scheduled pipeline validation — November 12, 2026

- Updated existing scheduler `FPL-bigquery-ingestion` to POST `{}` to the
  `fpl-refresh` executions API using OAuth with the dedicated `fpl-scheduler`
  service account. Workflows Invoker is granted at project level, its lowest
  supported scope; no BigQuery or Cloud Run grants were added to this identity.
- Compared scheduler settings before and after: name, enabled state, cron
  `0 */6 * * *`, timezone `America/Vancouver`, retry configuration, and
  180-second request deadline were preserved. There is exactly one scheduler in
  `us-central1`, targeting the workflow rather than ingestion directly.
- The initial force run received HTTP 403 while the new IAM grant propagated.
  After confirming no execution started, a retry successfully submitted workflow
  execution `589b4699-64df-4ac7-8cee-9c0835a0e4f2` through Cloud Scheduler.
- That workflow reached `SUCCEEDED` at `2026-11-12T05:53:13.364787981Z`.
- Ingestion execution `fpl-bigquery-ingestion-svmjn` succeeded at
  `2026-11-12T05:50:47.931956Z`. dbt execution `fpl-dbt-build-667n9` was created
  afterward, at `2026-11-12T05:51:19.050325Z`, and succeeded at
  `2026-11-12T05:53:06.568316Z`.
- The evaluation table modification time advanced from
  `2026-11-11T05:54:54.262Z` to `2026-11-12T05:53:01.279Z`; it contains 389 rows.
- The scheduling script's preflight guard was exercised during the active
  workflow: it refused retargeting before any IAM or scheduler changes.
- `bash -n`, `git diff --check`, and relative documentation link checks passed.
