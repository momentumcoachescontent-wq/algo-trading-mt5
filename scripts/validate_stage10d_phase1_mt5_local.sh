#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MT5_ROOT="${MT5_ROOT:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5}"
LOG_PATH_ARG="${1:-}"
STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
JSON_OUT="${2:-$REPO_ROOT/data/processed/stage10d_phase1_forward_gate_${STAMP}.json}"

cd "$REPO_ROOT"

LOG_PATHS=()
if [[ -n "$LOG_PATH_ARG" ]]; then
  if [[ ! -f "$LOG_PATH_ARG" ]]; then
    echo "ERROR: log file not found: $LOG_PATH_ARG" >&2
    exit 66
  fi
  LOG_PATHS+=("$LOG_PATH_ARG")
else
  DISCOVERED_LOGS="$(
    python3 python/pipeline/discover_stage10d_phase1_logs.py "$MT5_ROOT"
  )"

  while IFS= read -r discovered_log; do
    if [[ -n "$discovered_log" ]]; then
      LOG_PATHS+=("$discovered_log")
    fi
  done <<< "$DISCOVERED_LOGS"
fi

if [[ ${#LOG_PATHS[@]} -eq 0 ]]; then
  echo "ERROR: no Stage10D v4.43.1 logs selected." >&2
  exit 66
fi

echo "Stage10D Phase 1 local forward validation"
echo "MT5 root : $MT5_ROOT"
echo "Logs     :"
for log_path in "${LOG_PATHS[@]}"; do
  echo "  - $log_path"
done
echo "JSON out : $JSON_OUT"
echo

python3 python/pipeline/validate_stage10d_phase1_shadow_strict.py \
  "${LOG_PATHS[@]}" \
  --expected-magic 20260711 \
  --require-evaluation \
  --json-out "$JSON_OUT"
