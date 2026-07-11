#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MT5_ROOT="${MT5_ROOT:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5}"
LOG_PATH="${1:-}"
STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
JSON_OUT="${2:-$REPO_ROOT/data/processed/stage10d_phase1_forward_gate_${STAMP}.json}"

cd "$REPO_ROOT"

if [[ -z "$LOG_PATH" ]]; then
  LOG_PATH="$(python3 - "$MT5_ROOT" <<'PY'
import sys
from pathlib import Path

from python.pipeline.validate_stage10d_phase1_shadow import EA_MARKER, read_log

mt5_root = Path(sys.argv[1])
search_dirs = (
    mt5_root / "MQL5" / "Logs",
    mt5_root / "Logs",
)

candidates: list[Path] = []
for directory in search_dirs:
    if directory.is_dir():
        candidates.extend(directory.glob("*.log"))

matching: list[Path] = []
for path in candidates:
    try:
        if EA_MARKER in read_log(path):
            matching.append(path)
    except OSError:
        continue

if not matching:
    searched = ", ".join(str(path) for path in search_dirs)
    raise SystemExit(
        "No Stage10D v4.43.1 MT5 log found. Searched: " + searched
    )

latest = max(matching, key=lambda path: (path.stat().st_mtime_ns, path.name))
print(latest)
PY
)"
fi

if [[ ! -f "$LOG_PATH" ]]; then
  echo "ERROR: log file not found: $LOG_PATH" >&2
  exit 66
fi

echo "Stage10D Phase 1 local forward validation"
echo "MT5 root : $MT5_ROOT"
echo "Log      : $LOG_PATH"
echo "JSON out : $JSON_OUT"
echo

"$REPO_ROOT/scripts/validate_stage10d_phase1_forward.sh" \
  "$LOG_PATH" \
  "$JSON_OUT"
