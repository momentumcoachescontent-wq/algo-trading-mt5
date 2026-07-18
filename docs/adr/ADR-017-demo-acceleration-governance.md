# ADR-017 — Demo Acceleration Governance

## Status

Accepted for Stage 1 implementation and review.

This ADR authorizes governance artifacts, validation code, tests, and branch isolation only. It does not activate a new EA, change an existing EA, change Worker or Supabase production behavior, alter MT5 configuration, or authorize real capital.

## Context

Stage10C currently runs on a demo account. The active control has generated too little forward sample to evaluate the strategy efficiently. The project can accept more experimental risk in demo, but it must not lose causal attribution or replace challenger-specific gates with generic sample thresholds.

The program therefore needs to accelerate evidence through isolated challengers while preserving:

- v4.43.0 as the unchanged control;
- v4.43.1 as the D1 integrity and counterfactual observer;
- the Stage10A gate for Sleeve B;
- the approved Stage10D Donchian entry gate;
- account, identity, risk, and branch separation;
- the distinction between demo continuation and promotion to real capital.

## Decision

Create the Demo Acceleration program with five governed engines:

| Engine | Role | Stage 1 state |
|---|---|---|
| v4.43.0 | Stage10C control | Existing demo control; unchanged |
| v4.43.1 | D1 integrity observer | Existing shadow; order-disabled |
| Sleeve B SELL touch_025 | Independent SELL challenger | Planned; not authorized in Stage 1 |
| Frequency body015 | Single-variable frequency challenger | Planned; not authorized in Stage 1 |
| Stage10D Donchian | Continuation challenger | Offline research only |

The machine-readable source of truth is:

```text
configs/demo_acceleration/demo_acceleration_v1.json
```

The contract is validated by:

```text
python3 python/pipeline/validate_demo_acceleration_contract.py \
  configs/demo_acceleration/demo_acceleration_v1.json
```

## Risk decision

The Stage 1 contract records future demo limits but does not activate them:

```text
maximum experimental open risk = 2.00%
maximum same-direction USDJPY risk = 1.25%
maximum experimental positions = 3
daily new-entry block = 2.50%
weekly program pause = 5.00%
program drawdown stop = 7.00%
```

The control remains fixed at 0.25%. Sleeve B and Frequency are planned at 0.50% initial risk with a maximum of 0.75% after five clean executions. Donchian remains at zero execution risk until its full gate passes.

## Challenger-specific gates

### Sleeve B

The Stage10A continuity gate is inherited without replacement:

```text
minimum forward window = 16 weeks
minimum trades = 30
median_r > 0
top3_share < 40%
```

Operational pauses do not replace this gate.

### Frequency body015

The only permitted causal change is:

```text
body_c1_min: 0.25 -> 0.15
```

The `n=8` and `n=15` checkpoints are technical and demo-continuation checkpoints only. The proposed strong gate remains subject to a separate approval before it becomes a promotion rule.

### Donchian

The approved entry gate remains owned by Stage10D:

```text
minimum trades = 80
profit factor > 1.15
positive out-of-sample required
all four mandatory approved conditions required
```

Stage 1 references the approved 10-Jul decision and Stage10D charter rather than rewriting or weakening its four mandatory conditions. Donchian remains offline until the full gate passes.

## Isolation decision

- v4.43.0 and v4.43.1 remain in `DEMO_A`.
- Sleeve B is reserved for `DEMO_B`.
- Frequency body015 is reserved for `DEMO_C`.
- Donchian has no execution account while offline.
- Every engine has a unique strategy variant and Magic.
- Experimental engines may not share a netting account.
- Cross-engine position adoption is prohibited.
- Manual discretionary intervention is prohibited unless governed by a separately approved safety rule.

## Branch decision

Each future implementation remains isolated:

```text
agent/stage10c-observability-repair
agent/shadow-trade-ledger
agent/sleeve-b-demo-execution
agent/stage10c-frequency-body015-demo
agent/stage10d-phase2-data-readiness
```

No future execution change belongs in the Stage10D research PR.

## Consequences

### Positive

- Faster demo evidence without contaminating the control.
- Challenger-specific gates remain enforceable.
- Risk and identity become machine-verifiable.
- Future implementations have explicit branch boundaries.
- A governance-only stage cannot accidentally authorize execution.

### Negative

- Three demo account slots are required for preferred isolation.
- Additional telemetry and ledger work is required before activation.
- Frequency body015 still needs a separately approved strong gate.
- The four Donchian conditions remain governed by their canonical approval source and must not be paraphrased into weaker substitutes.

## Stage 1 exit decision

Stage 1 may close only when:

- the contract validates;
- all regression tests pass;
- v4.43.0 risk and parameters remain frozen;
- no challenger is activated;
- Stage10A and Stage10D gates are preserved;
- account, identity, risk, and branch isolation are explicit.
