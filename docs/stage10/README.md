# Stage10 Program Index

## Active program state

| Stage | Purpose | Current status |
|---|---|---|
| Stage10B | Controlled frequency pilot | Closed; not promoted |
| Stage10C | USDJPY-first governance reset and live core baseline | Active demo control; strategy unchanged |
| Stage10D | Momentum continuation challenger research | Phase 1 CLOSED / PASS; Phase 2 remains isolated offline research |
| Demo Acceleration | Isolated demo evidence acceleration | Stage 1 CLOSED / PASS; Stage 2 observability repair implemented, awaiting validation |

## Stage10C documents

- `STAGE10B5_CLOSURE.md`
- `STAGE10C_CONFIG_INPUT_PLAN.md`
- `STAGE10C_EA_LOCAL_GATE_INPUT_DESIGN.md`
- `STAGE10C_EXECUTION_SCOPE_PAYLOAD.md`
- `STAGE10C_IMPLEMENTATION_READINESS_PLAN.md`
- `STAGE10C_MASTER_DESIGN_CLOSURE.md`
- `STAGE10C_OBSERVABILITY_REPAIR.md`
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
- `DEMO_ACCELERATION_STAGE1_CLOSURE.md`
- `../adr/ADR-017-demo-acceleration-governance.md`
- `../../configs/demo_acceleration/demo_acceleration_v1.json`

## Program relationship

```text
Stage10C = demo execution control and governance baseline
Stage10D = isolated continuation challenger research
Demo Acceleration = isolated control, shadow and experimental evidence program
```

Demo Acceleration does not replace or relax Stage10C. It preserves the v4.43.0 control, keeps v4.43.1 order-disabled, inherits the Stage10A Sleeve B gate, and keeps Stage10D offline until its full gate passes.

## Demo Acceleration Stage 1 closure

Stage 1 closed with its canonical governance contract and subsequent hardening:

```text
contract_id=57d4efc4cf332d46c4cad9a5
PASS_GOVERNANCE_CONTRACT
reserved identities pinned
malformed contracts fail safely
planned challengers cannot become order-capable
activation_authorized=false
production_capital_authorized=false
```

It did not activate Sleeve B, Frequency body015 or Donchian, and did not change an EA, Worker, Supabase, MT5 input or capital authorization.

## Demo Acceleration Stage 2 boundary

Stage 2 repairs observability only:

```text
valid shadow ENTRY_READY is not ERROR
execution_mode is persisted
signal/governance/execution reasons are separated
order_ticket, deal_ticket and position_id are distinct
signal_eval_id supports explicit correlation
close matching updates one unambiguous row
failed signal persistence cannot return misleading HTTP 200
```

Implementation paths:

```text
infra/worker/src/observability.ts
infra/worker/src/index.ts
infra/supabase/migrations/006_stage10c_observability.sql
docs/stage10/STAGE10C_OBSERVABILITY_REPAIR.md
```

Stage 2 does not modify any EA or activate a challenger. Migration execution and Worker deployment require a separate user validation checkpoint.

## F5A.6 Pilar C disposition

Pilar C is absorbed into Stage10D:

- touch-gap instrumentation -> Stage10D Phase 2;
- missed-opportunity and dead-space audit -> Stage10D Phase 3;
- historical backtest population required by the challenger -> Stage10D Phase 2;
- path-quality reconstruction -> Stage10D Phase 2.

No separate Pilar C execution stream remains.

## Stage10D Phase 1 closure finding

The exact active v4.43.0 sources disproved the initial stale-cache hypothesis.

`CH4Signal::Evaluate()` generated the H4 BUY/SELL pattern independently of `bias_d1`; the bias only selected a diagnostic fail reason when no pattern existed. Therefore a raw candidate could be generated while D1 was neutral or opposite.

The v4.43.1 candidate separates:

```text
raw_h4_signal
filtered_h4_signal
```

Only a raw signal aligned with the discrete D1 bias can be promoted. Neutral or opposite candidates remain observable for research and are blocked before `ENTRY_READY`.

The final validator isolates the exact v4.43.1 EA marker and joins rotated MT5 logs when necessary. Events emitted by the active v4.43.0 control cannot satisfy or fail the shadow gate.

## Final Stage10D Phase 1 gate

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
```
