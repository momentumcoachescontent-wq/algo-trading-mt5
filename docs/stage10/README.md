# Stage10 Program Index

## Active program state

| Stage | Purpose | Current status |
|---|---|---|
| Stage10B | Controlled frequency pilot | Closed; not promoted |
| Stage10C | USDJPY-first governance reset and live core baseline | Active core; unchanged by Stage10D |
| Stage10D | Momentum continuation challenger research | Phase 1 compile/startup/replay/CI passed; first organic H4 evaluation pending |

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

## Program relationship

```text
Stage10C = production core and governance baseline
Stage10D = isolated challenger research
```

Stage10D does not replace or relax Stage10C. It investigates a separate continuation hypothesis.

## F5A.6 Pilar C disposition

Pilar C is absorbed into Stage10D:

- touch-gap instrumentation -> Stage10D Phase 2;
- missed-opportunity and dead-space audit -> Stage10D Phase 3;
- historical backtest population required by the challenger -> Stage10D Phase 2;
- path-quality reconstruction -> Stage10D Phase 2.

No separate Pilar C execution stream remains.

## Current Phase 1 finding

The exact active v4.43.0 sources disproved the initial stale-cache hypothesis.

`CH4Signal::Evaluate()` generated the H4 BUY/SELL pattern independently of `bias_d1`; the bias only selected a diagnostic fail reason when no pattern existed. Therefore a raw candidate could be generated while D1 was neutral or opposite.

The v4.43.1 candidate now separates:

```text
raw_h4_signal
filtered_h4_signal
```

Only a raw signal aligned with the discrete D1 bias can be promoted. Neutral or opposite candidates remain observable for research and are blocked before `ENTRY_READY`.

The final validator also isolates the exact v4.43.1 EA marker before evaluating a mixed MT5 daily log. Events emitted by the active v4.43.0 real EA cannot satisfy or fail the shadow gate.

## Current phase gate

```text
Phase 1 diagnosis = PASS
Phase 1 implementation = PASS
Phase 1 static/validator tests = PASS
Phase 1 MetaEditor compile = PASS
Phase 1 shadow startup safety = PASS
Phase 1 webhook authentication = PASS
Phase 1 Magic/boot isolation = PASS
Phase 1 July 8 contract replay = PASS
Phase 1 mixed-log isolation regression = PASS (GitHub Actions)
Phase 1 targeted CI = PASS
Phase 1 first organic H4 evaluation = PENDING
Phase 2 authorization = DENIED
```

No Donchian implementation or strategy backtest may begin while the organic H4 forward gate remains open.
