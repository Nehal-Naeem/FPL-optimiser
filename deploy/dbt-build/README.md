# dbt build Cloud Run job

`fpl-dbt-build` runs `dbt build --select '+mart_player_eval'` once and exits with
dbt's status. It builds the nine FPL models, excludes the starter seeds, and does
not ingest raw data. The existing model schema files declare no data tests yet.

## Setup and deployment

Run from the repository root with `gcloud`, `bq`, and Python 3 installed. The
deploying account needs permission to enable APIs, create datasets and service
accounts, grant IAM, submit builds, deploy jobs, and act as the runtime service
account. Reuse the existing `fpl-jobs` Artifact Registry repository and Cloud
Build identity configured for ingestion.

```sh
gcloud auth login
bash deploy/dbt-build/setup.sh
bash deploy/dbt-build/deploy.sh
```

Setup checks `fpl_raw`'s location, creates `fpl_analytics` in that location if
absent, and refuses an existing output dataset in a different location. It grants
`fpl-dbt@fpl-optimizer-511321.iam.gserviceaccount.com`:

- BigQuery Job User on the project.
- BigQuery Data Viewer on `fpl_raw`.
- BigQuery Data Editor on `fpl_analytics`.

The profile uses `method: oauth` and Application Default Credentials from the
attached Cloud Run identity. No local profile or service-account key is uploaded.
The deploy script uploads only an explicit allowlist of project source files and
deployment configuration. Cloud Build installs dependencies, installs locked dbt
packages, and parses the project before publishing the image.

Defaults: project `fpl-optimizer-511321`, region `us-central1`, repository
`fpl-jobs`, one task, one CPU, 1 GiB memory, 20-minute timeout, zero task retries.
dbt uses four threads and a 15-minute per-query timeout. The non-root runtime
writes logs and artifacts under `/tmp/dbt`; console output goes to Cloud Logging.
Local artifacts are ephemeral and are not uploaded to persistent storage.

Override `PROJECT_ID`, `REGION`, `DATASET_ID`, `BIGQUERY_LOCATION`, `JOB_NAME`,
`REPOSITORY`, or `SERVICE_ACCOUNT` for deployment. `BIGQUERY_LOCATION` defaults
to `US`; use the location printed by setup. Setup also accepts `RAW_DATASET` and
`SERVICE_ACCOUNT_NAME`. Match the deployment identity to any setup override.
Raw source declarations still target `fpl-optimizer-511321.fpl_raw`; changing
deployment variables alone does not retarget those sources.

## Execution and inspection

Deployment does not run the job. After raw ingestion succeeds:

```sh
gcloud run jobs execute fpl-dbt-build \
  --project=fpl-optimizer-511321 --region=us-central1 --wait
gcloud run jobs logs read fpl-dbt-build \
  --project=fpl-optimizer-511321 --region=us-central1 --limit=100
```

Use the [refresh workflow](../fpl-refresh/README.md) for the full pipeline. An
independent dbt rerun uses whatever raw snapshot is currently available. Avoid
overlapping job or workflow executions.

## Dependency updates

`requirements.in` pins stable dbt Core and adapter versions; `requirements.txt`
pins the complete resolved dependency set for Python 3.12. Update the input,
resolve all dependencies for Python 3.12, and rebuild to validate on Linux. Keep
the committed dbt package lockfile in sync with `packages.yml`. No package
installation or Git checkout occurs during job execution.

## Validation

The image build runs `pip check`, `dbt deps`, and `dbt parse`. Validate execution
against BigQuery after deployment; parsing does not prove SQL execution succeeds.
Confirm five staging views, three intermediate views, and the evaluation table
appear in `fpl_analytics`. Raw tables remain in `fpl_raw`.
