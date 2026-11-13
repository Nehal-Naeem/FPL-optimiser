#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
INGESTION_JOB="${INGESTION_JOB:-fpl-bigquery-ingestion}"
DBT_JOB="${DBT_JOB:-fpl-dbt-build}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-fpl-workflow}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud services enable workflows.googleapis.com workflowexecutions.googleapis.com \
    --project="$PROJECT_ID"
gcloud beta services identity create --service=workflows.googleapis.com \
    --project="$PROJECT_ID"
if [[ -z "$(gcloud iam service-accounts list --project="$PROJECT_ID" --filter="email=${SERVICE_ACCOUNT}" --format='value(email)')" ]]; then
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --project="$PROJECT_ID" --display-name="FPL refresh workflow"
fi
# v2 execution connectors poll regional operations, outside the job IAM resource.
if gcloud iam roles describe fplRunOperationViewer --project="$PROJECT_ID" > /dev/null 2>&1; then
    gcloud iam roles update fplRunOperationViewer --project="$PROJECT_ID" \
        --permissions=run.operations.get --stage=GA
else
    gcloud iam roles create fplRunOperationViewer --project="$PROJECT_ID" \
        --title="FPL Cloud Run operation reader" --permissions=run.operations.get --stage=GA
fi
for attempt in 1 2 3 4; do
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="projects/${PROJECT_ID}/roles/fplRunOperationViewer" --condition=None \
        --format='value(etag)'; then
        break
    fi
    [[ "$attempt" -lt 4 ]] || exit 1
    sleep 5
done
for job in "$INGESTION_JOB" "$DBT_JOB"; do
    # Retry idempotent grants briefly while a newly created identity propagates.
    for attempt in 1 2 3 4; do
        if gcloud run jobs add-iam-policy-binding "$job" \
            --project="$PROJECT_ID" --region="$REGION" \
            --member="serviceAccount:${SERVICE_ACCOUNT}" --role=roles/run.invoker \
            --format='value(etag)'; then
            break
        fi
        [[ "$attempt" -lt 4 ]] || exit 1
        sleep 5
    done
done
