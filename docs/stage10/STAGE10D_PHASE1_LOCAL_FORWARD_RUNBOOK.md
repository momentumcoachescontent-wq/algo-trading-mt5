# Stage10D Phase 1 — Local Forward Validation Runbook

## Purpose

Run the final Phase 1 gate directly against the active MetaTrader 5 daily log on the user's Mac after the first organic H4 evaluation.

The MT5 daily log contains messages from both:

```text
v4.43.0 real baseline
v4.43.1 shadow candidate
```

The final gate therefore uses the strict validator, which filters every input line by the exact v4.43.1 EA marker before checking order activity, webhook coverage, Magic, and D1/H4 snapshot integrity.

## Prerequisites

```text
v4.43.1 compiled
v4.43.1 attached to USDJPY H4
ExecutionScope=SHADOW_ONLY
AllowRealTrading=false
Magic=20260711
webhook secret configured locally
```

## Update the local repository

```bash
git fetch origin agent/stage10d-phase1-d1-context-closure
git switch agent/stage10d-phase1-d1-context-closure
git pull
```

## Automatic local validation

From the repository root:

```bash
bash scripts/validate_stage10d_phase1_mt5_local.sh
```

The script searches these standard MetaTrader 5 locations:

```text
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Logs
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/Logs
```

It selects the most recently modified `.log` containing the exact v4.43.1 EA marker and writes a timestamped JSON result under:

```text
data/processed/stage10d_phase1_forward_gate_<UTC_TIMESTAMP>.json
```

## Explicit log override

When the MT5 log was copied elsewhere:

```bash
bash scripts/validate_stage10d_phase1_mt5_local.sh \
  "/absolute/path/to/copied.log"
```

## Expected result

Final approval requires:

```text
PASS_PHASE1_FORWARD_GATE
```

A startup-only log exits with code `3` because no H4 evaluation exists yet. A contract or safety violation exits with code `2`.

## Checks performed

- Latest v4.43.1 session exists.
- Execution scope is `SHADOW_ONLY`.
- `order_send_allowed=false`.
- Magic is `20260711`.
- Init payload is capital-disabled.
- Authenticated `ea_init` webhook returned `200`.
- No v4.43.1 order-like event exists.
- At least one `[D1_CONTEXT_SNAPSHOT]` exists.
- Generated and consumed snapshot IDs match.
- Generated and consumed discrete bias match.
- Neutral or opposite D1 context never promotes a signal.
- Nonzero filtered signal equals both raw H4 signal and discrete D1 bias.
- Every shadow evaluation has an `EDGE_EVAL_WEBHOOK_OK` event.

## Important isolation rule

Events emitted by v4.43.0 cannot satisfy or fail the v4.43.1 gate. This prevents an interleaved real-EA trade or webhook from producing a false result.

## Phase boundary

This runbook closes only the Stage10D Phase 1 forward gate. It does not authorize Stage10D Phase 2 until the validation result is reviewed and Phase 1 is explicitly closed.
