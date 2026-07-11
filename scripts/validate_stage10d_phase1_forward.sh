#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/mt5.log [json-output]" >&2
  exit 64
fi

LOG_PATH="$1"
JSON_OUT="${2:-data/processed/stage10d_phase1_forward_gate.json}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT"
python3 python/pipeline/validate_stage10d_phase1_shadow.py \
  "$LOG_PATH" \
  --expected-magic 20260711 \
  --require-evaluation \
  --json-out "$JSON_OUT"
