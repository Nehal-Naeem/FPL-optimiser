#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
WORKFLOW_NAME="${WORKFLOW_NAME:-fpl-refresh}"
INGESTION_JOB="${INGESTION_JOB:-fpl-bigquery-ingestion}"
DBT_JOB="${DBT_JOB:-fpl-dbt-build}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-fpl-workflow@${PROJECT_ID}.iam.gserviceaccount.com}"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

gcloud workflows deploy "$WORKFLOW_NAME" \
    --project="$PROJECT_ID" --location="$REGION" \
    --source="${DEPLOY_DIR}/workflow.yml" --service-account="$SERVICE_ACCOUNT" \
    --set-env-vars="JOB_REGION=${REGION},INGESTION_JOB=${INGESTION_JOB},DBT_JOB=${DBT_JOB}"

echo "Deployed without execution or schedule. Run with:"
echo "gcloud workflows run ${WORKFLOW_NAME} --project=${PROJECT_ID} --location=${REGION}"
