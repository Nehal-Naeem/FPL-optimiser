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

## Published snapshot migration

The historical pipeline and projection models are deployed in production. The
public service enables published snapshot mode explicitly; the backend default
remains legacy for compatibility with other environments.
After completing [the pipeline rollout](../fpl-refresh/README.md), set
`FPL_USE_PUBLISHED_SNAPSHOT=true`. Grant the runtime Job User and table-level Data
Viewer on `fpl_analytics.mart_recommendation_snapshot`; it then needs no raw read
grants. Published mode uses one query/snapshot, includes nullable recent context,
component contributions and both scoring/display fixtures, and never silently
falls back if the published table is absent. API version conflicts remain 409.

Metadata adds `published`, `season` and `last_checked_at`. Freshness in published
mode uses successful collection checks, while `scores_updated_at` retains the
score calculation time. The UI distinguishes those timestamps, explains
incomplete historical coverage, and shows descriptive low-minutes/budget/club
exposure notes. Legacy-mode expected-point, starting-XI and captaincy limitations
remain. The production service is `fpl-web` in `us-central1`.

## Run with real history locally, without changing scheduled production

A prepared Python 3.12 dbt environment can run:

```sh
python scripts/local_refresh.py
cd frontend
npm run build
cd ..
bash scripts/serve_local.sh
```

The refresh uses ADC and creates `fpl_raw_localtest`, `fpl_build_localtest`, and
`fpl_analytics_localtest` in the existing project. It copies only the production
catalog schemas, fetches live FPL data, runs the same ingestion and candidate
publication code, and saves artifacts under `logs/local-refresh/<run UUID>/`.
Local stage claims are permitted only when all three datasets end in `_localtest`.
The local refresh command does not alter production Scheduler, Cloud Run, IAM,
raw tables or serving data.

The first refresh requests every current player; subsequent runs use checkpoints.
On failure the isolated lock is retained: inspect the run log and labelled
BigQuery jobs before recovery. A successful refresh releases the lock. Test
catalog/build tables have seven-day default expiration; canonical history/control
and published/archived tables explicitly retain their data for repeat testing.

The server exposes the built React frontend at `http://127.0.0.1:8000`, the API at
`/api`, and API docs at `/docs`. It uses the validated test snapshot with published
mode enabled. `PYTHON` can override the server's default `.venv-web/bin/python`;
`PORT` can select another local port. Production is deployed separately as `fpl-web`.

If a local dbt build fails after ingestion, fix the reported SQL/test failure and
resume that same isolated run without fetching histories again:

```sh
python scripts/local_refresh.py --resume RUN_UUID
```

Resume verifies global ownership, checks there are no pending/running BigQuery
jobs with that run label, verifies the raw manifest, and resets only the failed
unpublished build claim. It refuses to resume an already published run.


### Optional points planning

After the new projection models pass and publish, the same reader exposes the
experimental five-GW mode. No API endpoint or infrastructure is added. Choose the
points objective in the existing optimizer. See [methodology](../../docs/POINTS_PLANNER.md).
The local server at port 8000 serves the built UI and the validated `_localtest`
snapshot, including projection components and request-only minutes overrides.

## Reproducible private-first deployment

`bash deploy/frontend/deploy.sh` builds through Cloud Build from an allowlisted
context, tags the image by UTC deployment time, and deploys with authentication
required. It selects the validated **production** serving snapshot explicitly,
with zero minimum instances and at most three instances. Create the web identity
and grant table-level read access after the first production publication exists.
Only grant `allUsers` Cloud Run Invoker after private API and UI checks pass.
The script does not start a local server or change the scheduler.
