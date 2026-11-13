# Frontend deployment

The multi-stage image builds React and serves it from FastAPI on one origin.
Deployment is manual and separate from implementing the frontend. None of these
commands are run automatically. Run from the repository root.

## Access

Create a dedicated runtime service account `fpl-web` in project
`fpl-optimizer-511321`. Grant it `roles/bigquery.jobUser` at project level and
`roles/bigquery.dataViewer` on **only** the `fpl_raw` and `fpl_analytics` datasets.
The service does not write player data or need ingestion/deployment permissions.
Use the attached service-account identity, not a downloaded key. The deployer
needs permission to act as that identity and deploy Cloud Run services.

```sh
gcloud iam service-accounts create fpl-web --project=fpl-optimizer-511321 \
  --display-name="FPL frontend read-only runtime"
gcloud projects add-iam-policy-binding fpl-optimizer-511321 \
  --member=serviceAccount:fpl-web@fpl-optimizer-511321.iam.gserviceaccount.com \
  --role=roles/bigquery.jobUser
```

Grant the two dataset-scoped Data Viewer roles through each dataset's Sharing →
Permissions panel before deploying. Do not replace existing dataset access policies.

## Build and deploy

Use the existing Artifact Registry repository `fpl-jobs` (or substitute your repository).
Check its existence with `gcloud artifacts repositories list` before building.

```sh
docker build -f deploy/frontend/Dockerfile \
  -t us-central1-docker.pkg.dev/fpl-optimizer-511321/fpl-jobs/fpl-web:latest .
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/fpl-optimizer-511321/fpl-jobs/fpl-web:latest
gcloud run deploy fpl-web \
  --project=fpl-optimizer-511321 --region=us-central1 \
  --image=us-central1-docker.pkg.dev/fpl-optimizer-511321/fpl-jobs/fpl-web:latest \
  --service-account=fpl-web@fpl-optimizer-511321.iam.gserviceaccount.com \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=fpl-optimizer-511321,BIGQUERY_LOCATION=US \
  --cpu=1 --memory=1Gi --concurrency=4 --max-instances=3 --timeout=120 \
  --allow-unauthenticated
```

The final flag explicitly publishes the app for public use. Omit it to retain
authenticated access while validating a new service. Container builds require
network access to the npm and Python package registries.

Validate `/api/health`, `/api/players`, one real team import, and both optimizer
modes after deployment. Health is a process check; `/api/players` checks actual
BigQuery access. Inspect Cloud Run request errors and optimization status logs.
Roll back to the previous Cloud Run revision if validation fails. This deployment
does not modify the existing six-hour ingestion/dbt workflow.

## Configuration

| Environment variable | Default |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | `fpl-optimizer-511321` |
| `FPL_RAW_DATASET` | `fpl_raw` |
| `FPL_ANALYTICS_DATASET` | `fpl_analytics` |
| `BIGQUERY_LOCATION` | `US` |
| `PORT` | `8080` in the container |

The backend caches a read-only dataset for five minutes per process. Each
calculation uses one snapshot and rejects a mismatched client version with HTTP
409. Raw ingestion and mart publication are still separate writes; timestamps
identify their respective versions, not an atomic pipeline-wide snapshot.
Scores older than twelve hours are marked stale. A failed cache refresh returns
503 rather than silently falling back to old data.
