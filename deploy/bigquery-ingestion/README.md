# BigQuery ingestion Cloud Run job

The job runs `scripts/bigquery_ingestion.py` once and exits. It replaces the
`players`, `gameweeks`, `positions`, `teams`, and `fixtures` tables in `fpl_raw`
using the existing `WRITE_TRUNCATE` behavior. Each table replacement is separate;
a failed execution can leave a mix of old and new tables. Avoid overlapping runs.
The dataset and its existing table schemas must already be present.

## Infrastructure

The ingestion script uses Python 3.12, `requests`, and `google-cloud-bigquery`
inside a Docker container. Cloud Build builds the image, Artifact Registry stores
it, Cloud Run executes it, and Cloud Logging captures its output.

- Project: `fpl-optimizer-511321`; region: `us-central1`.
- Cloud Run job: `fpl-bigquery-ingestion`.
- Artifact Registry repository: `fpl-jobs`.
- Runtime service account:
  `fpl-ingestion@fpl-optimizer-511321.iam.gserviceaccount.com`.
- Required project IAM grants: `roles/bigquery.jobUser` and
  `roles/bigquery.dataEditor`.

The job executes ingestion only. Run it manually or use the
[`fpl-refresh` workflow](../fpl-refresh/README.md), which waits for ingestion to
succeed before executing the separate [`fpl-dbt-build` job](../dbt-build/README.md).
The existing Cloud Scheduler job now targets that workflow every six hours in
`America/Vancouver`, so scheduled refreshes include both ingestion and dbt.

To refresh the deployed job's data again, without rebuilding:

```sh
gcloud run jobs execute fpl-bigquery-ingestion \
  --project=fpl-optimizer-511321 --region=us-central1 --wait
```

## One-time Google Cloud setup

Run from the repository root with the Google Cloud CLI installed. The account
performing setup needs permission to enable APIs, manage service accounts and
IAM, create Artifact Registry repositories, submit builds, deploy Cloud Run jobs,
and act as the runtime service account. Billing must be enabled on the project.

```sh
gcloud auth login
export PROJECT_ID=fpl-optimizer-511321
export REGION=us-central1
export SERVICE_ACCOUNT="fpl-ingestion@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com bigquery.googleapis.com iam.googleapis.com \
  --project="$PROJECT_ID"

gcloud artifacts repositories create fpl-jobs \
  --project="$PROJECT_ID" --location="$REGION" --repository-format=docker

gcloud iam service-accounts create fpl-ingestion \
  --project="$PROJECT_ID" --display-name="FPL BigQuery ingestion"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role=roles/bigquery.jobUser --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role=roles/bigquery.dataEditor --condition=None
```

Choose a Cloud Run region appropriate for the BigQuery dataset's location. Skip
resource creation commands for resources that already exist. The runtime uses
its attached service account automatically; no credential key file is needed.
Both BigQuery roles are granted at project level. The runtime gets data editor
access across the project's BigQuery datasets, including `fpl_raw`, plus
permission to create BigQuery jobs.

Cloud Build uses a separate build service account. Identify that account with
`gcloud builds get-default-service-account --project="$PROJECT_ID" --region="$REGION"`
and ensure it has image upload access to the `fpl-jobs` repository, such as
`roles/artifactregistry.writer`, along with the source-bucket and logging access
required by Cloud Build.

## Deploy and execute

If `fpl_raw` and the service account already exist and the service account has
both `roles/bigquery.jobUser` and `roles/bigquery.dataEditor` at project level,
skip those setup steps. Ensure the APIs are enabled and the `fpl-jobs` Artifact
Registry repository exists, then continue from the repository root:

```sh
export PROJECT_ID=fpl-optimizer-511321
export REGION=us-central1
export SERVICE_ACCOUNT="fpl-ingestion@${PROJECT_ID}.iam.gserviceaccount.com"

bash deploy/bigquery-ingestion/deploy.sh

# Executes the ingestion and replaces the raw tables:
gcloud run jobs execute fpl-bigquery-ingestion \
  --project="$PROJECT_ID" --region="$REGION" --wait
```

The deployment script builds the image in Cloud Build, then creates or updates
the Cloud Run job. It uploads only the ingestion script, Dockerfile, and its
dedicated requirements. Docker is not required locally. Deployment does not
execute the ingestion or create a schedule.

Defaults: one task, one CPU, 512 MiB memory, a ten-minute timeout, and zero
automatic retries so partial table refreshes are visible for investigation.
HTTP errors and BigQuery load failures cause a failed job execution.
Output is sent to Cloud Logging.

Override `PROJECT_ID`, `REGION`, `DATASET_ID`, `JOB_NAME`, `REPOSITORY`, or
`SERVICE_ACCOUNT` as environment variables when running the deployment script.
For example:

```sh
REGION=europe-west2 bash deploy/bigquery-ingestion/deploy.sh
```

For local ingestion, install `deploy/bigquery-ingestion/requirements.txt` and run
`gcloud auth application-default login` before executing the Python script.
Local ingestion also replaces the BigQuery tables.

## Verify runtime permissions

Inspect the runtime service account's project IAM bindings:

```sh
gcloud projects get-iam-policy fpl-optimizer-511321 \
  --flatten=bindings \
  --filter='bindings.members:serviceAccount:fpl-ingestion@fpl-optimizer-511321.iam.gserviceaccount.com' \
  --format='table(bindings.role)'
```

Both `roles/bigquery.jobUser` and `roles/bigquery.dataEditor` should appear.
Use the project IAM commands in the setup section to manage these grants.
Allow a few minutes for IAM changes to propagate before execution. IAM changes
do not require rebuilding or redeploying the job.

References: [Cloud Run job deployment](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/deploy),
[Cloud Build image builds](https://docs.cloud.google.com/build/docs/running-builds/submit-build-via-cli-api),
[BigQuery roles](https://docs.cloud.google.com/bigquery/docs/access-control).
