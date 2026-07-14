# Stage10D Phase 2 — Canonical Data Gate Closure

## Status

**CLOSED / PASS — canonical USDJPY H4, D1 and M15 gap-governance subgate**

This checkpoint closes only the Phase 2 canonical data inventory, feed identity and gap-governance subgate. Stage10D Phase 2 remains **IN PROGRESS** and no EA, Worker, Supabase production, execution-policy or capital change is authorized.

## Verified source identity

```text
company: MetaQuotes Ltd.
server: MetaQuotes-Demo
terminal: MT5 on macOS/Wine
observed_server_offset: UTC+03:00
observed_at_utc: 2026-07-14T01:00:29Z
```

The offset is an observation for the recorded instant only. The pipeline does not infer a fixed historical offset and preserves source timestamps as broker-server wall-clock values.

## Executed regression gate

```text
tests.test_stage10d_gap_governance: 6/6 PASS
Stage10D Phase 2 CI: PASS
Stage10D Phase 1 regression CI: PASS
```

The feed profile is versioned at:

```text
configs/stage10d/metaquotes_demo_feed_v1.json
```

The raw gap policy remains versioned separately at:

```text
configs/stage10d/usdjpy_gap_governance_v1.json
```

## Canonical results

### USDJPY H4

```text
status: PASS_WITH_SESSION_CLOSURES_AND_GOVERNED_EXCLUSIONS
rows: 10161
structural_violation_count: 0
confirmed_session_gap_count: 10
governed_gap_count: 2
pending_calendar_gap_count: 0
unmatched_gap_count: 0
exit_code: 0
```

The two governed gaps contain four absent bars:

```text
2024-07-02 16:00:00
2024-07-02 20:00:00
2025-07-03 04:00:00
2025-07-03 08:00:00
```

No alternate local source contained those bars. No interpolation, copying from another feed or synthetic reconstruction is allowed. Any H4 feature, Donchian window, candidate or outcome window crossing one of these gaps must be excluded from promotion evidence.

### USDJPY D1

```text
status: PASS_WITH_CONFIRMED_SESSION_CLOSURES
rows: 1698
structural_violation_count: 0
confirmed_session_gap_count: 5
governed_gap_count: 0
pending_calendar_gap_count: 0
unmatched_gap_count: 0
exit_code: 0
```

The five exact holiday-adjacent intervals are accepted only through the verified feed profile. The implementation does not create a generic holiday calendar or infer historical timezone behavior.

### USDJPY M15

```text
status: PASS
rows: 4925
structural_violation_count: 0
confirmed_session_gap_count: 0
governed_gap_count: 0
pending_calendar_gap_count: 0
unmatched_gap_count: 0
exit_code: 0
```

M15 is accepted for its available coverage beginning in May 2026. It does not provide intrabar coverage for the full H4/D1 history from 2020.

## Governance interpretation

Raw quality evidence is preserved. H4 and D1 may retain `raw_quality_status=FAIL` because the raw auditor is deliberately unaware of feed-specific session exceptions. The governed decision layer converts only exact, previously enumerated intervals into non-blocking session closures and preserves the two H4 data gaps as mandatory exclusions.

Any new structural violation, unmatched gap, feed-profile mismatch or policy-version mismatch remains blocking.

## Remaining Phase 2 work

1. Produce canonical manifests and normalized artifacts carrying the verified feed identity and governed-gap metadata.
2. Implement and validate directional `touch_gap` fields using the Phase 0 formulas.
3. Implement prior-window Donchian features with the evaluated bar excluded.
4. Add reproducible ADX, EMA-extension, volatility and D1-alignment regime fields.
5. Reconstruct or explicitly mark unavailable MFE/MAE and `path_quality` using M15 coverage rules.
6. Build the normalized opportunity table for the Phase 3 dead-space audit.

No expectancy, challenger promotion or live/shadow execution conclusion is authorized by this checkpoint.
