# Stage10 Program Index

## Active program state

| Stage | Purpose | Current status |
|---|---|---|
| Stage10B | Controlled frequency pilot | Closed; not promoted |
| Stage10C | USDJPY-first governance reset and live core baseline | Active core; unchanged by Stage10D |
| Stage10D | Momentum continuation challenger research | Phase 1 CLOSED / PASS; Phase 2 awaits explicit authorization |
| Demo Acceleration | Isolated demo evidence acceleration | Stage 1 governance implemented; awaiting validation |

## Stage10C documents

- `STAGE10B5_CLOSURE.md`
- `STAGE10C_CONFIG_INPUT_PLAN.md`
- `STAGE10C_EA_LOCAL_GATE_INPUT_DESIGN.md`
- `STAGE10C_EXECUTION_SCOPE_PAYLOAD.md`
- `STAGE10C_IMPLEMENTATION_READINESS_PLAN.md`
- `STAGE10C_MASTER_DESIGN_CLOSURE.md`
- `STAGE10C_SUPABASE_DASHBOARD_PERSISTENCE_DESIGN.md`
- `STAGE10C_TOUCH_GAP_INSTRUMENTATION.md`
- `STAGE10C_WORKER_POLICY_DESIGN.md`

## Stage10D documents

- `STAGE10D_PROGRAM_CHARTER.md`
- `STAGE10D_PHASE0_FOUNDATION_AND_READINESS.md`
- `STAGE10D_PHASE1_D1_CONTEXT_CLOSURE.md`
- `STAGE10D_PHASE1_V4431_SOURCE_MANIFEST.md`
- `STAGE10D_PHASE1_OFFLINE_REPLAY_AND_FORWARD_GATE.md`
- `STAGE10D_PHASE1_LOCAL_FORWARD_RUNBOOK.md`
- `../adr/ADR-016-stage10d-donchian-breakout-challenger.md`

## Demo Acceleration documents

- `DEMO_ACCELERATION_PROGRAM_CHARTER.md`
- `../adr/ADR-017-demo-acceleration-governance.md`
- `../../configs/demo_acceleration/demo_acceleration_v1.json`

## Program relationship

```text
Stage10C = demo execution control and governance baseline
Stage10D = isolated continuation challenger research
Demo Acceleration = isolated control, shadow and experimental evidence program
```

Demo Acceleration does not replace or relax Stage10C. It preserves the v4.43.0 control, keeps v4.43.1 order-disabled, inherits the Stage10A Sleeve B gate, and keeps Stage10D offline until its full gate passes.

## Demo Acceleration Stage 1 boundary

Stage 1 defines machine-readable governance only:

```text
control risk and parameters frozen
challenger-specific gates preserved
account slots reserved
strategy identity and Magic reserved
portfolio risk envelope recorded
future implementation branches isolated
activation_authorized=false
production_capital_authorized=false
```

It does not activate Sleeve B, Frequency body015 or Donchian, and does not change an EA, Worker, Supabase, MT5 input or capital authorization.

## F5A.6 Pilar C disposition

Pilar C is absorbed into Stage10D:

- touch-gap instrumentation -> Stage10D Phase 2;
- missed-opportunity and dead-space audit -> Stage10D Phase 3;
- historical backtest population required by the challenger -> Stage10D Phase 2;
- path-quality reconstruction -> Stage10D Phase 2.

No separate Pilar C execution stream remains.

## Phase 1 closure finding

The exact active v4.43.0 sources disproved the initial stale-cache hypothesis.

`CH4Signal::Evaluate()` generated the H4 BUY/SELL pattern independently of `bias_d1`; the bias only selected a diagnostic fail reason when no pattern existed. Therefore a raw candidate could be generated while D1 was neutral or opposite.

The v4.43.1 candidate now separates:

```text
raw_h4_signal
filtered_h4_signal
```

Only a raw signal aligned with the discrete D1 bias can be promoted. Neutral or opposite candidates remain observable for research and are blocked before `ENTRY_READY`.

The final validator isolates the exact v4.43.1 EA marker and joins rotated MT5 logs when necessary. Events emitted by the active v4.43.0 real EA cannot satisfy or fail the shadow gate.

## Final Phase 1 gate

```text
Phase 1 diagnosis = PASS
Phase 1 implementation = PASS
Phase 1 static/validator tests = PASS
Phase 1 MetaEditor compile = PASS
Phase 1 shadow startup safety = PASS
Phase 1 webhook authentication = PASS
Phase 1 Magic/boot isolation = PASS
Phase 1 July 8 contract replay = PASS
Phase 1 mixed-log isolation regression = PASS
Phase 1 rotated-log discovery = PASS
Phase 1 targeted CI = PASS
Phase 1 organic H4 evaluations = 2 PASS / 0 violations
Phase 1 final validator = PASS_PHASE1_FORWARD_GATE
Phase 1 status = CLOSED / PASS
Phase 2 authorization = AWAITING EXPLICIT USER APPROVAL
```

No Donchian implementation or Phase 2 strategy work may begin until that approval is given.
