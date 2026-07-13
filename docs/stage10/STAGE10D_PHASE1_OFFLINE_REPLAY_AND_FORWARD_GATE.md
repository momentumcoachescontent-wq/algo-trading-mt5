# Stage10D Phase 1 — Offline Replay and Forward Gate

## Status

```text
Offline contract replay: PASS
Static and validator tests: PASS
Shadow startup validation: PASS_STARTUP_PENDING_EVALUATION
Final forward H4 gate: PENDING
Phase 2 authorization: DENIED until the forward gate passes
```

This document records the work completed while the FX market was closed. It does not replace the first organic H4 evaluation required to close Phase 1.

## Root-cause correction

Inspection of the exact active v4.43.0 source disproved the earlier stale-cache hypothesis.

The actual defect was orchestration order inside `CH4Signal::Evaluate()`:

```text
raw H4 pattern -> H4 signal
```

The discrete D1 bias was used to choose a diagnostic reason when no pattern existed, but it did not gate a valid raw BUY/SELL pattern before candidate telemetry and downstream handling.

The corrected v4.43.1 contract is:

```text
raw H4 pattern
-> preserve as raw_h4_signal for research
-> verify canonical D1 snapshot integrity
-> require raw direction == discrete D1 bias
-> emit filtered_h4_signal
-> only filtered_h4_signal may continue downstream
```

A raw candidate while D1 is neutral is therefore not itself evidence of stale state. It is allowed as research telemetry, but it must never be promoted to an executable signal.

## July 8 recorded contract replay

The replay uses the two recorded events that exposed the defect. It is a deterministic contract replay, not a price backtest.

| Evaluation | D1 structure | Weighted bias | Discrete bias | Raw H4 candidate | v4.43.1 filtered | Reason | Result |
|---|---:|---:|---:|---:|---:|---|---|
| 2026-07-08 00:00 | -1 | +0.400 | 0 | BUY | 0 | `d1_neutral_blocks_h4_signal` | PASS |
| 2026-07-08 04:00 | -1 | +0.400 | 0 | BUY | 0 | `d1_neutral_blocks_h4_signal` | PASS |

Result:

```text
events_total=2
events_passed=2
defective_promotions_prevented=2
PASS
```

The replay proves that the corrected promotion rule neutralizes the exact two recorded candidates that motivated Phase 1.

## Test result

The combined local suite passes 22 tests covering:

- neutral D1 blocks raw BUY and SELL;
- opposite D1 direction blocks the candidate;
- aligned D1/H4 direction is promoted;
- snapshot mismatch fails closed;
- raw and filtered signals remain separate;
- v4.43.1 consumes the canonical snapshot identity;
- payload contains weighted/discrete context and snapshot fields;
- source contains no committed webhook secret;
- v31 include isolation;
- July 8 replay;
- shadow startup validation;
- Magic isolation;
- authenticated webhook requirement;
- detection of illegal neutral-signal promotion.

Validation command:

```bash
python3 -m unittest discover -s tests -v
```

## Shadow startup evidence

The latest validated v4.43.1 session has:

```text
version=v4.43.1
execution_mode=SHADOW_ONLY
capital_enabled=false
order_send_allowed=false
magic=20260711
webhook ea_init status=200
order-like events=0
```

Automated status:

```text
PASS_STARTUP_PENDING_EVALUATION
```

The pending state is expected because the market was closed and the latest session contained no new H4 evaluation.

## Forward validator

`python/pipeline/validate_stage10d_phase1_shadow.py` scopes itself to the latest v4.43.1 session and verifies:

1. `SHADOW_ONLY` and `order_send_allowed=false`.
2. Magic equals `20260711`.
3. Init payload is capital-disabled.
4. `ea_init` webhook returned status 200.
5. No order-like event occurred.
6. Every `D1_CONTEXT_SNAPSHOT` has matching generated and consumed IDs.
7. Consumed discrete bias equals the canonical bias.
8. Neutral D1 never promotes a signal.
9. Opposite D1/H4 directions never promote a signal.
10. Any nonzero filtered signal equals both raw signal and discrete D1 bias.
11. Evaluation webhook coverage is present.

Startup-only command:

```bash
python3 python/pipeline/validate_stage10d_phase1_shadow.py /path/to/log \
  --expected-magic 20260711
```

Final Phase 1 command:

```bash
scripts/validate_stage10d_phase1_forward.sh /path/to/log
```

The final command uses `--require-evaluation`; it exits nonzero when no H4 evaluation exists or any contract violation is found.

## Final gate required after market open

Phase 1 closes only when the latest v4.43.1 session produces at least one organic H4 evaluation and the validator returns:

```text
PASS_PHASE1_FORWARD_GATE
```

Required evidence:

```text
[D1_CONTEXT_SNAPSHOT]
snapshot_match=true
snapshot_id == h4_consumed_snapshot_id
bias_discrete == h4_consumed_bias
filtered_h4_signal obeys D1 gate
[EDGE_EVAL_WEBHOOK_OK] status=200
no order event
```

Until that evidence exists, Phase 2 remains blocked.
