# Stage10D Phase 2 — Governed Canonical Manifests

## Status

**IMPLEMENTED — pending execution against local canonical exports**

This block converts the closed USDJPY H4/D1/M15 data-gap checkpoint into reproducible governed manifest artifacts. It does not modify raw CSV files, synthesize bars, convert broker-server timestamps to UTC, change Stage10C parameters or authorize live/shadow execution.

## Contract

Each governed manifest preserves both layers:

```text
raw_quality_status
  physical CSV audit result before exceptions

governance_status
  explicit decision from the committed gap policy and verified feed profile
```

A raw H4/D1 `FAIL` remains visible. Research eligibility is granted only when every non-weekend gap is either:

- an exact confirmed source-session closure enumerated in the policy and promoted by the verified feed profile; or
- a governed data gap with mandatory analytic-window exclusion.

New unmatched gaps and structural violations remain blocking.

## Identity inputs

```text
source CSV SHA-256
raw data_manifest_id
gap policy version and SHA-256
feed profile version and SHA-256
broker company
account server
terminal environment
symbol and timeframe
timestamp semantics
governance status
excluded bar timestamps
```

The governed manifest ID is deterministic for those identity fields. The generated timestamp is observational and does not alter the ID.

## Feed semantics

Current verified profile:

```text
broker_company       MetaQuotes Ltd.
account_server       MetaQuotes-Demo
terminal_environment mt5-macos-wine
observed offset      UTC+03:00 at 2026-07-14T01:00:29Z
```

The historical UTC offset remains intentionally uninferred. Source timestamps remain MetaQuotes-Demo broker-server wall-clock values.

## Coverage classification

```text
H4/D1 PRIMARY_CANONICAL_BAR_HISTORY
M15   PARTIAL_INTRABAR_PATH_COVERAGE
```

M15 coverage must not be represented as complete intrabar history for the full H4/D1 range.

## Outputs

For each timeframe:

```text
<stem>_governed_manifest.json
<stem>_raw_manifest.json
<stem>_raw_quality.json
<stem>_gap_governance.json
```

## Local execution

```bash
for TF in H4 D1 M15; do
  python3 python/pipeline/build_stage10d_phase2_governed_manifest.py \
    "exports/USDJPY_${TF}.csv" \
    --policy configs/stage10d/usdjpy_gap_governance_v1.json \
    --feed-profile configs/stage10d/metaquotes_demo_feed_v1.json \
    --symbol USDJPY \
    --timeframe "$TF" \
    --output-dir data/processed/stage10d_phase2/canonical_manifests

done
```

Expected exit code is `0` for H4, D1 and M15.

Expected governance statuses:

```text
H4  PASS_WITH_SESSION_CLOSURES_AND_GOVERNED_EXCLUSIONS
D1  PASS_WITH_CONFIRMED_SESSION_CLOSURES
M15 PASS
```

H4 must contain exactly these excluded bar timestamps:

```text
2024-07-02 16:00:00
2024-07-02 20:00:00
2025-07-03 04:00:00
2025-07-03 08:00:00
```

## Gate

This block closes only when:

```text
three governed manifests exit 0
three governed manifest IDs are present
source checksums are present
policy/feed checksums are present
synthetic=false for all three
H4 excluded_bar_times match the four governed bars
D1 excluded_bar_times is empty
M15 coverage_classification is PARTIAL_INTRABAR_PATH_COVERAGE
pending_calendar_gap_count=0 for all three
unmatched_gap_count=0 for all three
structural_violation_count=0 for all three
```

After this gate, Phase 2 proceeds to executable directional `touch_gap` instrumentation. No strategy expectancy conclusion belongs to this block.
