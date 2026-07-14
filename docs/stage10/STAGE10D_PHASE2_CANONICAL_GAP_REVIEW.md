# Stage10D Phase 2 — Canonical Gap Review

## Status

**IN PROGRESS — source integrity passed; session-gap reconciliation pending**

This checkpoint is based on the primary local candidates:

```text
exports/USDJPY_H4.csv
exports/USDJPY_D1.csv
exports/USDJPY_M15.csv
```

No source file has been modified, merged or patched.

## Structural integrity result

All three files are parseable. The following structural checks passed:

```text
                    H4      D1      M15
duplicates           0       0        0
source order          0       0        0
OHLC violations       0       0        0
nonpositive volume    0       0        0
unknown gaps          0       0        0
```

M15 passes the current gate with 4,925 rows and coverage beginning in May 2026. It is suitable for recent path reconstruction only and does not provide intrabar coverage for the full 2020–2026 H4/D1 period.

## H4 and D1 gap result

H4 contains 12 `missing_export_segment` gaps and D1 contains 5. The D1 gaps overlap Christmas/New Year periods already visible in H4.

The observed gaps divide into two governance groups.

### Candidate broker holiday/session closures

The following periods are candidates for an explicit broker-session exception calendar. They must not be silently inferred by month/day alone:

```text
2020-12-24 / 2020-12-28
2020-12-31 / 2021-01-04
2022-12-23 / 2022-12-26
2022-12-30 / 2023-01-02
2023-12-25 / 2023-12-26
2023-12-29 / 2024-01-02
2024-12-25 / 2024-12-26
2025-01-01 / 2025-01-02
2025-12-24 / 2025-12-26
2025-12-31 / 2026-01-02
```

Five D1 gaps are contained within those periods. These candidates remain non-passing until broker/feed identity and broker-server timezone semantics are recorded and the exact exceptions are approved.

### Unresolved H4 data gaps

Two H4 windows are not accepted as normal holiday closures:

```text
2024-07-02 12:00:00 -> 2024-07-03 00:00:00
missing H4 bars: 2024-07-02 16:00:00, 2024-07-02 20:00:00

2025-07-03 00:00:00 -> 2025-07-03 12:00:00
missing H4 bars: 2025-07-03 04:00:00, 2025-07-03 08:00:00
```

These remain genuine missing-segment findings unless alternate same-feed sources provide consistent bar evidence or a fresh MT5 export restores them.

## Alternate-source inspection

Use the read-only inspector to search historical copies without modifying the primary export:

```bash
python3 python/pipeline/inspect_stage10d_phase2_gap_sources.py \
  exports/USDJPY_H4.csv \
  . \
  --symbol USDJPY \
  --timeframe H4 \
  --gap "2024-07-02 12:00:00|2024-07-03 00:00:00" \
  --gap "2025-07-03 00:00:00|2025-07-03 12:00:00" \
  --json-out data/processed/stage10d_phase2/usdjpy_h4_gap_sources.json
```

Possible outcomes:

```text
COMPLETE_CONSISTENT_REPAIR_EVIDENCE
PARTIAL_REPAIR_EVIDENCE
CONFLICTING_REPAIR_EVIDENCE
NO_REPAIR_EVIDENCE
```

The inspector never patches the primary CSV. Evidence from copies can justify a targeted re-export or a separately governed repaired dataset, but it cannot silently alter canonical history.

## Promotion constraint

Until this review is closed:

```text
H4 canonical manifest = FAIL
D1 canonical manifest = FAIL pending explicit session calendar
M15 canonical manifest = provisional PASS with limited coverage
Phase 3 dead-space audit = BLOCKED
Donchian expectancy analysis = BLOCKED
real or shadow Stage10D execution = NOT AUTHORIZED
```
