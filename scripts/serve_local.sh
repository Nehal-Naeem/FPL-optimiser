#!/usr/bin/env bash
# Serve the built frontend and API against the isolated, validated local-test snapshot.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-fpl-optimizer-511321}"
export FPL_RAW_DATASET="${FPL_RAW_DATASET:-fpl_raw_localtest}"
export FPL_ANALYTICS_DATASET="${FPL_ANALYTICS_DATASET:-fpl_analytics_localtest}"
export BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-US}"
export FPL_USE_PUBLISHED_SNAPSHOT=true
PYTHON="${PYTHON:-$ROOT/.venv-web/bin/python}"
[[ -f frontend/dist/index.html ]] || { echo 'Build frontend first: cd frontend && npm run build' >&2; exit 1; }
exec "$PYTHON" -m uvicorn backend.app:app --host 127.0.0.1 --port "${PORT:-8000}"
