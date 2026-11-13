#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
WORKFLOW_NAME="${WORKFLOW_NAME:-fpl-refresh}"
SCHEDULER_JOB="${SCHEDULER_JOB:-FPL-bigquery-ingestion}"
SCHEDULER_REGION="${SCHEDULER_REGION:-$REGION}"
SCHEDULER_ACCOUNT_NAME="${SCHEDULER_ACCOUNT_NAME:-fpl-scheduler}"
SCHEDULER_ACCOUNT="${SCHEDULER_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
INGESTION_JOB="${INGESTION_JOB:-fpl-bigquery-ingestion}"
DBT_JOB="${DBT_JOB:-fpl-dbt-build}"

# Read before changing anything. An existing scheduler and deployed workflow are required.
BEFORE="$(gcloud scheduler jobs describe "$SCHEDULER_JOB" --project="$PROJECT_ID" \
    --location="$SCHEDULER_REGION" --format=json)"
SCHEDULE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["schedule"])' <<< "$BEFORE")"
TIME_ZONE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["timeZone"])' <<< "$BEFORE")"
gcloud workflows describe "$WORKFLOW_NAME" --project="$PROJECT_ID" \
    --location="$REGION" --format='value(state)'

ACTIVE="$(gcloud workflows executions list "$WORKFLOW_NAME" --project="$PROJECT_ID" \
    --location="$REGION" --filter='state=ACTIVE OR state=QUEUED' --format='value(name)')"
if [[ -n "$ACTIVE" ]]; then
    echo "A refresh workflow is active or queued; wait before retargeting." >&2
    exit 1
fi
for job in "$INGESTION_JOB" "$DBT_JOB"; do
    gcloud run jobs executions list --job="$job" --project="$PROJECT_ID" \
        --region="$REGION" --format=json | python3 -c '
import json, sys
active = [e["metadata"]["name"] for e in json.load(sys.stdin)
          if not e.get("status", {}).get("completionTime")]
if active:
    sys.exit("Job executions still active: " + ", ".join(active))
'
done

gcloud services enable cloudscheduler.googleapis.com --project="$PROJECT_ID"
if [[ -z "$(gcloud iam service-accounts list --project="$PROJECT_ID" --filter="email=${SCHEDULER_ACCOUNT}" --format='value(email)')" ]]; then
    gcloud iam service-accounts create "$SCHEDULER_ACCOUNT_NAME" \
        --project="$PROJECT_ID" --display-name="FPL refresh scheduler"
fi
# Workflows Invoker's lowest supported IAM scope is the project.
for attempt in 1 2 3 4; do
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SCHEDULER_ACCOUNT}" \
        --role=roles/workflows.invoker --condition=None --format='value(etag)'; then
        break
    fi
    [[ "$attempt" -lt 4 ]] || exit 1
    sleep 5
done

# Update in place; explicitly preserve the current cadence and timezone.
# Existing enabled/paused state, attempt deadline, and retry settings are retained.
gcloud scheduler jobs update http "$SCHEDULER_JOB" --project="$PROJECT_ID" \
    --location="$SCHEDULER_REGION" \
    --description="Refresh FPL raw data and dbt analytics through fpl-refresh" \
    --schedule="$SCHEDULE" --time-zone="$TIME_ZONE" \
    --uri="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/workflows/${WORKFLOW_NAME}/executions" \
    --http-method=POST --message-body='{}' \
    --update-headers=Content-Type=application/json \
    --oauth-service-account-email="$SCHEDULER_ACCOUNT" \
    --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform

echo "Retargeted existing scheduler; no force run was issued."
echo "Preserved schedule: ${SCHEDULE} (${TIME_ZONE})."
