#!/usr/bin/env bash
# Operator-only provisioning. No ingestion or deployment occurs.
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
RAW_DATASET="${RAW_DATASET:-fpl_raw}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-fpl-ingestion}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
PYTHON="${PYTHON:-.venv-web/bin/python}"
[[ "$RAW_DATASET" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCATION="$(bq show --format=prettyjson "${PROJECT_ID}:${RAW_DATASET}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["location"])')"
if [[ -z "$(gcloud iam service-accounts list --project="$PROJECT_ID" --filter="email=${SERVICE_ACCOUNT}" --format='value(email)')" ]]; then
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" --project="$PROJECT_ID" --display-name="FPL ingestion"
fi
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role=roles/bigquery.jobUser --condition=None --format='value(etag)'
bq --project_id="$PROJECT_ID" --location="$LOCATION" query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${RAW_DATASET}\` TO 'serviceAccount:${SERVICE_ACCOUNT}'"
# The replacement dataset grant is established before removing the old broad grant.
HAS_BROAD_GRANT="$(gcloud projects get-iam-policy "$PROJECT_ID" --format=json | python3 -c '
import json,sys
member="serviceAccount:"+sys.argv[1]
print("true" if any(b["role"]=="roles/bigquery.dataEditor" and not b.get("condition")
                   and member in b["members"] for b in json.load(sys.stdin).get("bindings",[])) else "false")
' "$SERVICE_ACCOUNT")"
if [[ "$HAS_BROAD_GRANT" == true ]]; then
    gcloud projects remove-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role=roles/bigquery.dataEditor --condition=None --format='value(etag)'
fi
GOOGLE_CLOUD_PROJECT="$PROJECT_ID" FPL_RAW_DATASET="$RAW_DATASET" BIGQUERY_LOCATION="$LOCATION" \
    "$PYTHON" "${DEPLOY_DIR}/../../scripts/setup_history.py"
