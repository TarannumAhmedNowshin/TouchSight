#!/usr/bin/env bash
# One-time setup:  bash setup.sh
set -e
cd "$(dirname "$0")"
PY=python3
if ! $PY -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
  echo "Python 3.10+ needed. Found: $($PY --version)"; exit 1
fi
[ -d .venv ] || $PY -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ environment ready"
[ -f .env ] || { echo "⚠️  .env missing: cp .env.example .env and add your keys"; exit 1; }
python test_keys.py
