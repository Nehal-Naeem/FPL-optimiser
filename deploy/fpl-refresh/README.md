# FPL refresh workflow

`fpl-refresh` runs two separate Cloud Run jobs in order:

1. Execute `fpl-bigquery-ingestion` and wait for successful completion.
2. Execute `fpl-dbt-build` and wait for successful completion.
3. Return both Cloud Run execution resource names.

The Workflows Cloud Run connector waits for completion. Unhandled connector or
job errors fail the workflow; ingestion failure prevents the dbt step from
starting. No explicit workflow retry policy is installed. Connector timeouts are
15 minutes for ingestion and 25 minutes for dbt, longer than their task timeouts.

## Setup and deployment

Deploy both Cloud Run jobs first. Then, from the repository root:

```sh
bash deploy/fpl-refresh/setup.sh
bash deploy/fpl-refresh/deploy.sh
```

Setup enables Workflows APIs, explicitly provisions the Google-managed Workflows
service agent, and creates the dedicated identity
`fpl-workflow@fpl-optimizer-511321.iam.gserviceaccount.com`, granting Cloud Run
Invoker on each job individually. A project-scoped custom role grants only
`run.operations.get`, which the v2 connector needs to poll regional execution
operations. The setup account needs permission to manage this custom role.
The service-agent command uses the gcloud beta component; install it with
`gcloud components install beta` if needed. The workflow identity has no BigQuery
access. The caller deploying the workflow must be allowed to act as this service account; callers
executing it need Workflows execution permission, such as Workflows Invoker.

Defaults are project `fpl-optimizer-511321`, region `us-central1`, workflow
`fpl-refresh`, and the job names above. Scripts accept `PROJECT_ID`, `REGION`,
`INGESTION_JOB`, and `DBT_JOB`; deployment also accepts `WORKFLOW_NAME` and
`SERVICE_ACCOUNT`, while setup accepts `SERVICE_ACCOUNT_NAME`. Match identity
overrides between setup and deployment. Both jobs must be in the selected region.

Deployment does not execute the workflow or create a Cloud Scheduler trigger.

## Schedule the complete pipeline

Scheduler `FPL-bigquery-ingestion` now triggers this workflow, despite retaining
its original ingestion-specific name. It runs at 00:00, 06:00, 12:00, and 18:00 in
`America/Vancouver` (`0 */6 * * *`). Both raw tables and the dbt evaluation table
are refreshed on each successful pipeline execution.

To configure the existing scheduler after deploying the workflow:

```sh
bash deploy/fpl-refresh/schedule.sh
```

The script requires an existing scheduler, checks for active or queued workflow
executions and unfinished executions of both jobs, and refuses to change the
target while a refresh is running. This is a preflight check, not a global lock;
avoid manual refreshes during the change.

It creates `fpl-scheduler@fpl-optimizer-511321.iam.gserviceaccount.com` and grants
Workflows Invoker at project level, the lowest scope supported by that role. This
identity receives no BigQuery or Cloud Run execution grants. The existing
`fpl-workflow` runtime identity continues to execute the two Cloud Run jobs.
The account running setup must be able to manage service accounts and project
IAM, update the scheduler, and act as the scheduler identity.

The scheduler sends an OAuth-authenticated POST with JSON body `{}` to the
Workflows executions API. The script updates the existing target in place and
explicitly preserves its current schedule and timezone. Enabled/paused state,
retry configuration, and request deadline remain unchanged. No second scheduler
or automatic force run is created.

Overrides: `PROJECT_ID`, `REGION`, `WORKFLOW_NAME`, `SCHEDULER_JOB`,
`SCHEDULER_REGION`, `SCHEDULER_ACCOUNT_NAME`, `INGESTION_JOB`, and `DBT_JOB`.

To test through the scheduler, first confirm the pipeline is idle, then run:

```sh
gcloud scheduler jobs run FPL-bigquery-ingestion \
  --project=fpl-optimizer-511321 --location=us-central1
```

Scheduler success confirms submission, not completion. Check the resulting
workflow execution reaches `SUCCEEDED`, then inspect the two job executions and
the modification time of `fpl_analytics.mart_player_eval`. Do not create a second
schedule targeting ingestion directly, as it would bypass the dbt dependency.
New IAM grants can take several minutes to propagate. If an initial force run
returns `PERMISSION_DENIED`, verify the grant, allow propagation, and confirm no
workflow was started before retrying the scheduler.

## Run and inspect

```sh
gcloud workflows run fpl-refresh \
  --project=fpl-optimizer-511321 --location=us-central1
gcloud workflows executions list fpl-refresh \
  --project=fpl-optimizer-511321 --location=us-central1
```

Inspect execution details and errors in the Workflows console or with
`gcloud workflows executions describe EXECUTION_ID --workflow=fpl-refresh
--project=fpl-optimizer-511321 --location=us-central1`. Inspect each job's Cloud
Logging output for ingestion and SQL failures.

Avoid overlapping refreshes, including direct executions of either job. There is
no global lock, and one task per job does not prevent multiple executions.
Ingestion replaces tables independently; the workflow does not make that refresh
atomic. A dbt failure can also leave some transformed models updated. Correct the
failure and rerun the appropriate job; no automatic rollback is provided.

## Acceptance checks

See [recorded deployment validation](VALIDATION.md) for the verified executions.

- Run dbt independently and verify all nine models in `fpl_analytics`.
- Run this workflow and verify dbt starts after ingestion completes successfully.
- In an isolated test workflow, point the ingestion step at a failing test job
  and confirm no dbt execution starts. Point the dbt step at a failing test job
  and confirm the workflow fails after the first step succeeds. Do not alter
  production job configuration to simulate failures.

Source freshness policies, new data tests, global locking, persistent
dbt artifact storage, and automated deployment remain follow-up work.
