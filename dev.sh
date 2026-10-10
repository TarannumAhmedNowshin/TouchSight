#!/usr/bin/env bash
# Start TouchSight locally:  bash dev.sh   then open http://localhost:3000
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Run 'bash setup.sh' first."; exit 1; }
command -v node >/dev/null || { echo "Node.js 20+ is needed for the frontend: https://nodejs.org"; exit 1; }
source .venv/bin/activate
uvicorn app:app --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM
cd frontend
[ -d node_modules ] || npm install --no-audit --no-fund
npm run dev
