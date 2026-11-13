#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
DATASET_ID="${DATASET_ID:-fpl_analytics}"
BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-US}"
JOB_NAME="${JOB_NAME:-fpl-dbt-build}"
REPOSITORY="${REPOSITORY:-fpl-jobs}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-fpl-dbt@${PROJECT_ID}.iam.gserviceaccount.com}"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${JOB_NAME}:$(date -u +%Y%m%d%H%M%S)"

if [[ -z "$(gcloud auth list --filter=status:ACTIVE --format='value(account)')" ]]; then
    echo "Run gcloud auth login first." >&2
    exit 1
fi

# Explicit allowlist: no local databases, credentials, logs, or generated artifacts.
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp "${DEPLOY_DIR}/Dockerfile" "${DEPLOY_DIR}/requirements.txt" "${DEPLOY_DIR}/profiles.yml" "$BUILD_DIR/"
mkdir "$BUILD_DIR/project"
for item in dbt_project.yml packages.yml package-lock.yml models macros seeds; do
    cp -R "${DEPLOY_DIR}/../../dbt/fpl_optimizer/${item}" "$BUILD_DIR/project/"
done

gcloud builds submit "$BUILD_DIR" \
    --project="$PROJECT_ID" --region="$REGION" --tag="$IMAGE"
gcloud run jobs deploy "$JOB_NAME" \
    --project="$PROJECT_ID" --region="$REGION" --image="$IMAGE" \
    --service-account="$SERVICE_ACCOUNT" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},DBT_DATASET=${DATASET_ID},BIGQUERY_LOCATION=${BIGQUERY_LOCATION}" \
    --tasks=1 --parallelism=1 --max-retries=0 \
    --task-timeout=1200s --cpu=1 --memory=1Gi

echo "Deployed without execution. Run independently with:"
echo "gcloud run jobs execute ${JOB_NAME} --project=${PROJECT_ID} --region=${REGION} --wait"
