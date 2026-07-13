# Stage10D Phase 1 — D1 Context Closure

## Status

**CLOSED — PASS**

Stage10D Phase 1 is formally closed after the isolated v4.43.1 candidate compiled, started safely in `SHADOW_ONLY`, passed the July 8 contract replay, passed targeted CI, and passed the organic H4 forward gate on July 13, 2026.

Final validator result:

```text
status=PASS_PHASE1_FORWARD_GATE
evaluations=2
edge_webhook_ok=2
failed_checks=0
order_like_events=0
```

Phase 2 is technically unblocked by the Phase 1 gate, but it must not begin until explicitly authorized.

## 1. Sources verified

Original files recovered from the active MT5 installation:

| File | SHA-256 |
|---|---|
| `EMA_MTF_v4430_stage10c_usdjpy_first_governance_reset.mq5` | `f4b49710552ef5fc4def01c665975c0041c73bd3d14141888cf73a3b7d49d83b` |
| `D1Context.mqh` | `7c907a83c236b193ed8e16bfa40fdbd5384e07e48d2d48aea86113c88d7114c8` |
| `H4Signal.mqh` | `ef477d7d4d6f0e07f3813204a3b2475bd7af7d8c4be5e99ed88a3ec822856593` |

The supplied package manifest matched all three files.

## 2. Corrected root cause

The initial stale-cache hypothesis was disproved by inspection of the exact active source.

`CH4Signal::Evaluate()` calculated `pattern_bull` and `pattern_bear` independently of the discrete D1 bias. The bias was used only to select a diagnostic reason when no H4 pattern existed. Therefore a raw H4 BUY/SELL candidate could exist while D1 was neutral or opposite.

Correct classification:

```text
raw_candidate_while_d1_neutral_or_opposite
```

The restart correlation was incidental. The candidate disappeared when the two-candle H4 pattern disappeared, not because a stale D1 cache was refreshed.

## 3. Corrected v4.43.1 contract

The candidate is isolated from the active v4.43.0 modules:

```text
MQL5/Include/v31/D1Context.mqh
MQL5/Include/v31/H4Signal.mqh
MQL5/Experts/Advisors/EMA_MTF_v4431_stage10c_d1_context_integrity.mq5
```

Promotion rules:

| Raw H4 | Discrete D1 | Filtered H4 | Reason |
|---:|---:|---:|---|
| +1 | +1 | +1 | `signal_ok` |
| -1 | -1 | -1 | `signal_ok` |
| ±1 | 0 | 0 | `d1_neutral_blocks_h4_signal` |
| +1 | -1 | 0 | `d1_bias_blocks_opposite_h4_signal` |
| -1 | +1 | 0 | `d1_bias_blocks_opposite_h4_signal` |

A raw candidate remains observable for research. Only the filtered signal can enter the Stage10C decision waterfall.

## 4. Canonical D1 snapshot integrity

The EA resolves one canonical D1 snapshot per H4 evaluation and passes the same bias, reason and snapshot identity to H4.

Required invariant:

```text
bias_d1_snapshot_id == h4_consumed_d1_snapshot_id
bias_d1_discrete == h4_consumed_bias
```

Any mismatch fails closed:

```text
filtered_h4_signal=0
block_reason=d1_context_snapshot_mismatch
order_send_allowed=false
```

Telemetry includes:

```text
bias_d1_weighted
bias_d1_discrete
bias_d1_structure
bias_d1_data_valid
bias_d1_context_reason
bias_d1_snapshot_id
h4_consumed_d1_snapshot_id
d1_snapshot_match
h4_raw_signal
h4_signal
```

## 5. Security and isolation

Validated controls:

```text
version=v4.43.1
execution_mode=SHADOW_ONLY
capital_enabled=false
order_send_allowed=false
Magic=20260711
webhook ea_init status=200
order-like events=0
```

The v4.43.1 source contains no committed webhook secret. The active v4.43.0 real EA remains unchanged with independent Magic `20260527`.

The strict validator filters mixed MT5 daily logs by the exact v4.43.1 EA marker, so v4.43.0 events cannot satisfy or fail the shadow gate.

## 6. Offline and CI validation

The July 8 deterministic contract replay passed:

```text
events_total=2
events_passed=2
defective_promotions_prevented=2
```

Targeted GitHub Actions passed, covering:

- Python module compilation;
- Bash syntax;
- D1/H4 contract tests;
- replay tests;
- strict mixed-log isolation;
- rotated-log discovery;
- direct command-line execution of the discovery helper.

## 7. Organic H4 forward evidence

The local final gate ran against the MT5 log stream and returned:

```text
status=PASS_PHASE1_FORWARD_GATE
session_lines=33
expected_magic=20260711
observed_magic=20260711
evaluations=2
edge_webhook_ok=2
failed_checks=0
```

Evaluations validated:

| Eval time | Bias D1 | Raw H4 | Filtered H4 | Snapshot match | Violations |
|---|---:|---:|---:|---|---:|
| 2026-07-13 00:00 | +1 | 0 | 0 | true | 0 |
| 2026-07-13 04:00 | +1 | 0 | 0 | true | 0 |

All final checks passed:

```text
latest_v4431_session=PASS
shadow_execution_scope=PASS
magic_isolation=PASS
init_payload_safety=PASS
ea_init_webhook=PASS
no_order_activity=PASS
d1_h4_evaluation_contract=PASS
evaluation_webhook=PASS
```

## 8. Phase 1 decision

```text
Phase 1 diagnosis = PASS
Phase 1 implementation = PASS
Phase 1 static and validator tests = PASS
Phase 1 MetaEditor compile = PASS
Phase 1 shadow startup safety = PASS
Phase 1 webhook authentication = PASS
Phase 1 Magic/boot isolation = PASS
Phase 1 July 8 replay = PASS
Phase 1 mixed-log and rotated-log isolation = PASS
Phase 1 targeted CI = PASS
Phase 1 organic H4 forward gate = PASS
Phase 1 status = CLOSED / PASS
```

## 9. Phase boundary

Phase 1 closure does not itself authorize strategy changes or live capital for the challenger.

The recommended next block is Stage10D Phase 2 design and instrumentation:

```text
touch-gap instrumentation
historical challenger population
path-quality reconstruction
Donchian continuation research in isolated shadow/offline scope
```

No Stage10C production risk, touch, SL, TP, compression or governance parameter should change as part of the Phase 1 closure.
