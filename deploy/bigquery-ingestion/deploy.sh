#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
DATASET_ID="${DATASET_ID:-fpl_raw}"
JOB_NAME="${JOB_NAME:-fpl-bigquery-ingestion}"
REPOSITORY="${REPOSITORY:-fpl-jobs}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-fpl-ingestion@${PROJECT_ID}.iam.gserviceaccount.com}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${JOB_NAME}:$(date -u +%Y%m%d%H%M%S)"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$(gcloud auth list --filter=status:ACTIVE --format='value(account)')" ]]; then
    echo "No active Google Cloud login. Run gcloud auth login first." >&2
    exit 1
fi

# Upload only the job's three source files, excluding local data and credentials.
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp "${DEPLOY_DIR}/Dockerfile" "${DEPLOY_DIR}/requirements.txt" "$BUILD_DIR/"
cp "${DEPLOY_DIR}/../../scripts/bigquery_ingestion.py" "$BUILD_DIR/"

gcloud builds submit "$BUILD_DIR" \
    --project="$PROJECT_ID" --region="$REGION" --tag="$IMAGE"

gcloud run jobs deploy "$JOB_NAME" \
    --project="$PROJECT_ID" --region="$REGION" --image="$IMAGE" \
    --service-account="$SERVICE_ACCOUNT" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},BIGQUERY_DATASET=${DATASET_ID}" \
    --tasks=1 --parallelism=1 --max-retries=0 \
    --task-timeout=600s --cpu=1 --memory=512Mi

echo "Job deployed. To refresh BigQuery, run:"
echo "gcloud run jobs execute ${JOB_NAME} --project=${PROJECT_ID} --region=${REGION} --wait"
