#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
FPL_SEASON="${FPL_SEASON:-2026-27}"
BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-US}"
TASK_TIMEOUT="${TASK_TIMEOUT:-600s}"
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

# Upload only allowlisted runtime files, excluding local data and credentials.
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
cp "${DEPLOY_DIR}/Dockerfile" "${DEPLOY_DIR}/requirements.txt" "$BUILD_DIR/"
for source in bigquery_ingestion.py history_ingestion.py pipeline.py; do
    cp "${DEPLOY_DIR}/../../scripts/${source}" "$BUILD_DIR/"
done

gcloud builds submit "$BUILD_DIR" \
    --project="$PROJECT_ID" --region="$REGION" --tag="$IMAGE"

gcloud run jobs deploy "$JOB_NAME" \
    --project="$PROJECT_ID" --region="$REGION" --image="$IMAGE" \
    --service-account="$SERVICE_ACCOUNT" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},BIGQUERY_DATASET=${DATASET_ID},FPL_SEASON=${FPL_SEASON},BIGQUERY_LOCATION=${BIGQUERY_LOCATION}" \
    --tasks=1 --parallelism=1 --max-retries=0 \
    --task-timeout="$TASK_TIMEOUT" --cpu=1 --memory=512Mi

echo "Deployed without execution. Run the complete refresh through the configured workflow."
echo "See deploy/fpl-refresh/README.md for rollout and recovery."
