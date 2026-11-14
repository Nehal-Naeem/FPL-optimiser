#!/usr/bin/env bash
# Build an allowlisted context and deploy privately; publish only after smoke checks.
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-fpl-optimizer-511321}"
REGION="${REGION:-us-central1}"
IMAGE_TAG="${IMAGE_TAG:-$(date -u +%Y%m%d%H%M%S)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/fpl-jobs/fpl-web:${IMAGE_TAG}"
SERVICE_ACCOUNT="fpl-web@${PROJECT_ID}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
python3 - "$ROOT" "$BUILD_DIR" "$IMAGE" <<'PY'
from pathlib import Path
import shutil,sys,json
root,out,image=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
ignore=shutil.ignore_patterns('node_modules','dist','test-results','playwright-report','__pycache__','.pytest_cache','*.tsbuildinfo','.env*','*.pem','*.key')
for folder in ('backend','frontend'):
    shutil.copytree(root/folder,out/folder,ignore=ignore)
(out/'deploy/frontend').mkdir(parents=True)
shutil.copy(root/'deploy/frontend/Dockerfile',out/'deploy/frontend/Dockerfile')
shutil.copy(root/'.dockerignore',out/'.dockerignore')
(out/'cloudbuild.json').write_text(json.dumps({'steps':[{'name':'gcr.io/cloud-builders/docker','args':['build','-f','deploy/frontend/Dockerfile','-t',image,'.']}],'images':[image]}))
PY
gcloud builds submit "$BUILD_DIR" --project="$PROJECT_ID" --region="$REGION" --config="$BUILD_DIR/cloudbuild.json"
if [[ "${BUILD_ONLY:-false}" == true ]]; then
  printf 'Built image: %s\n' "$IMAGE"
  exit 0
fi
ACCESS_ARGS=(--no-allow-unauthenticated)
if [[ -n "${PREVIEW_TAG:-}" ]]; then
  ACCESS_ARGS=(--no-traffic --tag="$PREVIEW_TAG")
fi
gcloud run deploy fpl-web --project="$PROJECT_ID" --region="$REGION" --image="$IMAGE" \
  --service-account="$SERVICE_ACCOUNT" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},BIGQUERY_LOCATION=US,FPL_RAW_DATASET=fpl_raw,FPL_ANALYTICS_DATASET=fpl_analytics" \
  --cpu=1 --memory=1Gi --concurrency=4 --min-instances=0 --max-instances=3 --timeout=120 \
  "${ACCESS_ARGS[@]}" --quiet
printf 'Deployment image: %s\n' "$IMAGE"
