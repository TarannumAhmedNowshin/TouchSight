#!/usr/bin/env bash
# Run engine + web app locally with auto-reload.   Usage: bash dev.sh   ->  http://localhost:3000
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Run 'bash setup.sh' first."; exit 1; }
command -v node >/dev/null || { echo "Node.js 20+ is needed for the web app: https://nodejs.org"; exit 1; }
source .venv/bin/activate

# Local-only conveniences: detailed errors and the sample-authoring endpoint. Never set these in production.
export DEBUG_ERRORS=1 ALLOW_SAMPLE_UPLOAD=1

uvicorn app:app --port 8000 --reload --reload-exclude ".venv/*" --reload-exclude "frontend/*" &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM

cd frontend
[ -d node_modules ] || npm ci --no-audit --no-fund
npm run dev
