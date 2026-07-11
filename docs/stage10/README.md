# Stage10 Program Index

## Active program state

| Stage | Purpose | Current status |
|---|---|---|
| Stage10B | Controlled frequency pilot | Closed; not promoted |
| Stage10C | USDJPY-first governance reset and live core baseline | Active core; unchanged by Stage10D |
| Stage10D | Momentum continuation challenger research | Phase 0 closed; Phase 1 pending review |

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

## Stage10D foundation documents

- `STAGE10D_PROGRAM_CHARTER.md`
- `STAGE10D_PHASE0_FOUNDATION_AND_READINESS.md`
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

## Current phase gate

Phase 0 is closed.

The next permitted activity is Stage10D Phase 1 — D1 Context Closure. No Donchian implementation or strategy backtest may begin before Phase 1 is reviewed and closed.