#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
DATASET_ID="${DATASET_ID:-fpl_analytics}"
RAW_DATASET="${RAW_DATASET:-fpl_raw}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-fpl-dbt}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Dataset names are interpolated into SQL identifiers below.
[[ "$DATASET_ID" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]
[[ "$RAW_DATASET" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com bigquery.googleapis.com iam.googleapis.com \
    --project="$PROJECT_ID"

RAW_LOCATION="$(bq show --format=prettyjson "${PROJECT_ID}:${RAW_DATASET}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["location"])')"
if bq show --format=prettyjson "${PROJECT_ID}:${DATASET_ID}" > /dev/null 2>&1; then
    OUTPUT_LOCATION="$(bq show --format=prettyjson "${PROJECT_ID}:${DATASET_ID}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["location"])')"
    if [[ "$RAW_LOCATION" != "$OUTPUT_LOCATION" ]]; then
        echo "Raw and output dataset locations differ; refusing setup." >&2
        exit 1
    fi
else
    bq --project_id="$PROJECT_ID" --location="$RAW_LOCATION" mk --dataset "${PROJECT_ID}:${DATASET_ID}"
fi

if [[ -z "$(gcloud iam service-accounts list --project="$PROJECT_ID" --filter="email=${SERVICE_ACCOUNT}" --format='value(email)')" ]]; then
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --project="$PROJECT_ID" --display-name="FPL dbt transformations"
fi
# Newly created identities can take a few seconds to propagate to project IAM.
for attempt in 1 2 3 4; do
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SERVICE_ACCOUNT}" --role=roles/bigquery.jobUser \
        --condition=None --format='value(etag)'; then
        break
    fi
    [[ "$attempt" -lt 4 ]] || exit 1
    sleep 5
done

# GRANT preserves other dataset access entries.
bq --project_id="$PROJECT_ID" --location="$RAW_LOCATION" query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`${PROJECT_ID}.${RAW_DATASET}\` TO 'serviceAccount:${SERVICE_ACCOUNT}'"
bq --project_id="$PROJECT_ID" --location="$RAW_LOCATION" query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${DATASET_ID}\` TO 'serviceAccount:${SERVICE_ACCOUNT}'"
echo "Setup complete. Deploy with BIGQUERY_LOCATION=${RAW_LOCATION}."
