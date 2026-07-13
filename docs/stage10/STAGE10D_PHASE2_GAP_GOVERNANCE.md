# Stage10D Phase 2 — Gap Governance

## Status

**IN PROGRESS — raw evidence preserved; governed exclusions defined**

This document records how Stage10D Phase 2 handles missing bars without rewriting source history.

## Evidence checkpoint

The canonical local candidates under `exports/` were parsed successfully.

```text
USDJPY H4  rows=10161  duplicates=0  order=0  ohlc=0  volume=0  unknown=0
USDJPY D1  rows=1698   duplicates=0  order=0  ohlc=0  volume=0  unknown=0
USDJPY M15 rows=4925   duplicates=0  order=0  ohlc=0  volume=0  unknown=0
```

M15 passed the raw gate with coverage beginning in May 2026.

H4 and D1 failed only because weekday timestamps were absent. The gap-source comparison found four H4 bars missing from the primary export and all four parseable local alternate sources:

```text
2024-07-02 16:00:00
2024-07-02 20:00:00
2025-07-03 04:00:00
2025-07-03 08:00:00
```

There is no valid local evidence for reconstructing those bars.

## Non-negotiable policy

- Raw CSV files and raw quality reports remain unchanged.
- Missing bars are never interpolated, copied from another feed or synthesized.
- Any H4 feature, Donchian window, candidate or outcome path crossing one of the four missing timestamps is excluded from promotion evidence.
- The exclusion must be reproducible from the committed policy file.
- Holiday-adjacent gaps remain pending until broker/feed identity and server-timezone semantics are verified.

## Policy artifact

```text
configs/stage10d/usdjpy_gap_governance_v1.json
```

The policy distinguishes:

```text
GOVERNED_DATA_GAP
PENDING_BROKER_CALENDAR_CONFIRMATION
```

`GOVERNED_DATA_GAP` permits analysis only with exclusion of windows crossing the gap.

`PENDING_BROKER_CALENDAR_CONFIRMATION` blocks the final canonical manifest until the broker calendar and server timezone are documented.

## Governance statuses

```text
PASS
PASS_WITH_GOVERNED_EXCLUSIONS
PENDING_BROKER_CALENDAR
FAIL_UNGOVERNED_GAPS
FAIL_STRUCTURAL
```

Structural failures always take precedence over gap policy.

## Local evaluation

```bash
python3 python/pipeline/evaluate_stage10d_phase2_gap_governance.py \
  exports/USDJPY_H4.csv \
  --policy configs/stage10d/usdjpy_gap_governance_v1.json \
  --symbol USDJPY \
  --timeframe H4 \
  --json-out data/processed/stage10d_phase2/usdjpy_h4_gap_governance.json
```

Repeat for D1 and M15.

Expected checkpoint before broker-calendar verification:

```text
H4  PENDING_BROKER_CALENDAR  governed_gap_count=2
D1  PENDING_BROKER_CALENDAR  governed_gap_count=0
M15 PASS
```

## Remaining gate

Phase 2 cannot mark H4 or D1 canonical until the following metadata is explicit:

```text
broker/feed identity
MT5 server/account identity
broker-server timezone or offset convention
holiday/session calendar evidence or documented observed-session policy
```

No EA, Worker, Supabase production or capital permission changes are included.
