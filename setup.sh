#!/usr/bin/env bash
# One-time local setup: Python venv, dependencies, provider check.   Usage: bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
$PY -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null \
  || { echo "Python 3.10+ is required (found: $($PY --version 2>&1))."; exit 1; }

[ -d .venv ] || $PY -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements-dev.txt -q
echo "Environment ready."

if [ ! -f .env ]; then
  echo "No .env yet: run 'cp .env.example .env' and add your API keys, then rerun."
  exit 1
fi
python scripts/check_keys.py
