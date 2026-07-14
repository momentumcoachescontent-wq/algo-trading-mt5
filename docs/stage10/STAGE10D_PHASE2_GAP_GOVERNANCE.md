# Stage10D Phase 2 — Gap Governance

## Status

**IN PROGRESS — feed identity verified; exact source closures confirmed**

This document records how Stage10D Phase 2 handles missing bars without rewriting source history.

## Evidence checkpoint

The canonical local candidates under `exports/` were parsed successfully.

```text
USDJPY H4  rows=10161  duplicates=0  order=0  ohlc=0  volume=0  unknown=0
USDJPY D1  rows=1698   duplicates=0  order=0  ohlc=0  volume=0  unknown=0
USDJPY M15 rows=4925   duplicates=0  order=0  ohlc=0  volume=0  unknown=0
```

M15 passed the raw gate with coverage beginning in May 2026.

H4 and D1 failed the raw gate only because weekday timestamps were absent. The gap-source comparison found four H4 bars missing from the primary export and all four parseable local alternate sources:

```text
2024-07-02 16:00:00
2024-07-02 20:00:00
2025-07-03 04:00:00
2025-07-03 08:00:00
```

There is no valid local evidence for reconstructing those bars.

## Verified feed identity

The MT5 runtime reported:

```text
broker_company = MetaQuotes Ltd.
account_server = MetaQuotes-Demo
observed_at_utc = 2026-07-14T01:00:29Z
server_time = 2026-07-14 04:00:29
offset = UTC+03:00
terminal_environment = mt5-macos-wine
```

The committed feed profile is:

```text
configs/stage10d/metaquotes_demo_feed_v1.json
```

The UTC+03:00 observation is valid only for the recorded instant. The project does not infer a fixed historical UTC offset or a generic MetaQuotes-Demo DST schedule. Source timestamps remain broker-server wall-clock values.

## Non-negotiable policy

- Raw CSV files and raw quality reports remain unchanged.
- Missing bars are never interpolated, copied from another feed or synthesized.
- Any H4 feature, Donchian window, candidate or outcome path crossing one of the four July missing timestamps is excluded from promotion evidence.
- The exclusion must be reproducible from the committed policy file.
- Holiday-adjacent intervals are accepted only when they match an exact rule already enumerated in the policy and the verified feed profile explicitly allows that policy version.
- New or unmatched gaps remain blocking.

## Policy artifacts

```text
configs/stage10d/usdjpy_gap_governance_v1.json
configs/stage10d/metaquotes_demo_feed_v1.json
```

The governance model distinguishes:

```text
CONFIRMED_SOURCE_SESSION_CLOSURE
GOVERNED_DATA_GAP
PENDING_BROKER_CALENDAR_CONFIRMATION
```

`CONFIRMED_SOURCE_SESSION_CLOSURE` permits the exact enumerated interval without synthetic bars or window exclusion. It is dataset-specific and does not establish a generic broker holiday calendar.

`GOVERNED_DATA_GAP` permits analysis only with exclusion of windows crossing the gap.

`PENDING_BROKER_CALENDAR_CONFIRMATION` remains blocking when no matching verified feed profile is supplied.

## Governance statuses

```text
PASS
PASS_WITH_CONFIRMED_SESSION_CLOSURES
PASS_WITH_GOVERNED_EXCLUSIONS
PASS_WITH_SESSION_CLOSURES_AND_GOVERNED_EXCLUSIONS
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
  --feed-profile configs/stage10d/metaquotes_demo_feed_v1.json \
  --symbol USDJPY \
  --timeframe H4 \
  --json-out data/processed/stage10d_phase2/usdjpy_h4_gap_governance_verified.json
```

Repeat for D1 and M15.

Expected verified checkpoint:

```text
H4  PASS_WITH_SESSION_CLOSURES_AND_GOVERNED_EXCLUSIONS
    confirmed_session_gap_count=10
    governed_gap_count=2
    pending_calendar_gap_count=0
    unmatched_gap_count=0

D1  PASS_WITH_CONFIRMED_SESSION_CLOSURES
    confirmed_session_gap_count=5
    governed_gap_count=0
    pending_calendar_gap_count=0
    unmatched_gap_count=0

M15 PASS
```

## Remaining Phase 2 gate

The canonical gap-governance gate can close after the verified local run reproduces the expected statuses and artifacts. Phase 2 itself remains open for normalized `touch_gap`, prior-window Donchian, regime, path-quality and opportunity-table implementation.

No EA, Worker, Supabase production or capital permission changes are included.
