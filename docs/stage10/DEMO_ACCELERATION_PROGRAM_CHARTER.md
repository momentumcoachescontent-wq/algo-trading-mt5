# Demo Acceleration Program Charter

## Status

**Stage 1 — CLOSED / PASS**

The governance, identity, risk-envelope, challenger-gate, and branch-isolation contract has been implemented and validated locally and in CI. This charter does not activate a challenger or authorize any new order path.

## Objective

Increase the speed of legitimate demo evidence without modifying the Stage10C control or weakening existing promotion standards.

The program accelerates evidence through independent experimental sleeves rather than by simply increasing the size of the existing control.

## Non-negotiable principles

1. v4.43.0 remains the unchanged control.
2. v4.43.1 remains `SHADOW_ONLY` until a separate change authorizes otherwise.
3. Sleeve B keeps the complete Stage10A gate.
4. Donchian keeps the complete Stage10D gate.
5. Generic `n=8/15/30` checkpoints cannot replace inherited gates.
6. Only one causal parameter may change in Frequency body015.
7. Experimental execution must be isolated by account, identity, Magic, and branch.
8. Demo evidence cannot authorize real capital automatically.
9. `ENTRY_READY` remains distinct from `ORDER_ALLOWED`.
10. Stage10D remains offline until its own program phases and gate are complete.

## Machine-readable contract

```text
configs/demo_acceleration/demo_acceleration_v1.json
```

The contract is the source of truth for:

- program status;
- account reservations;
- engine identities;
- Magic numbers;
- initial and maximum demo risk;
- portfolio limits;
- parameter deltas;
- inherited gates;
- future branch boundaries;
- Stage 1 closure criteria.

## Engine matrix

| Engine | Account | Mode | Risk | Stage 1 state |
|---|---|---|---:|---|
| v4.43.0 control | DEMO_A | Demo control execution | 0.25% | Existing; frozen |
| v4.43.1 D1 integrity | DEMO_A | Shadow only | 0% | Existing; order-disabled |
| Sleeve B SELL touch_025 | DEMO_B | Planned demo experimental | 0.50% to 0.75% | Not authorized |
| Frequency body015 | DEMO_C | Planned demo experimental | 0.50% to 0.75% | Not authorized |
| Stage10D Donchian | Unassigned | Offline only | 0% | Research only |

## Control boundary

The following v4.43.0 fields are frozen:

```text
EMA period
ADX minimum
body C1 minimum
confirmation
SL ATR
TP ATR
sessions
Friday guard
governance
risk = 0.25%
```

Any change to one of these fields invalidates the control relationship and must occur in a separate challenger.

## Sleeve B contract

### Purpose

Collect an independent USDJPY SELL population using the approved `touch_025` sleeve.

### Planned demo risk

```text
initial = 0.50%
maximum = 0.75%
minimum clean executions before escalation = 5
```

### Continuity gate

The Stage10A gate remains authoritative:

```text
minimum forward window = 16 weeks
minimum trades = 30
median_r > 0
top3_share < 40%
```

The following are operational pause rules, not replacements for the continuity gate:

- duplicate order;
- identity mismatch;
- risk above configured value;
- review after four consecutive losses;
- pause at cumulative result less than or equal to -5R.

## Frequency body015 contract

### Causal delta

```text
control body_c1_min = 0.25
challenger body_c1_min = 0.15
```

No other entry, management, session, risk-governance, or confirmation field may change in the same experiment.

### Planned demo risk

```text
initial = 0.50%
maximum = 0.75%
minimum clean executions before escalation = 5
```

### Checkpoints

`n=8` is a technical checkpoint only. It verifies clean execution, sizing, telemetry, and absence of duplicate orders.

`n=15` is a provisional demo-continuation checkpoint only. It cannot promote the strategy.

The proposed `n=30` strong gate requires a separate approval before becoming authoritative.

## Stage10D Donchian contract

Stage10D remains governed by ADR-016 and the Stage10D charter.

### Data source

The canonical source is same-feed MetaQuotes-Demo MT5 CSV with governed H4/D1 data and limited M15 path coverage. Windows crossing governed H4 gaps are excluded. Synthetic data cannot support promotion.

### Entry gate

```text
minimum trades = 80
profit factor > 1.15
positive out-of-sample required
all four mandatory conditions from the approved 10-Jul decision required
```

Software correctness, absence of look-ahead, and clean data are prerequisites. They do not replace the entry gate.

Donchian cannot receive a demo execution account or non-zero execution risk until the complete gate passes.

## Portfolio risk envelope

The planned future demo program may not exceed:

```text
experimental open risk = 2.00%
same-direction USDJPY risk = 1.25%
experimental positions = 3
daily new-entry block = 2.50%
weekly program pause = 5.00%
program drawdown stop = 7.00%
```

These are recorded limits, not an activation instruction.

## Identity and account isolation

Every engine requires:

```text
experiment_id
strategy_variant
execution_mode
magic_number
guard_version
risk_pct
config_hash
code_commit_sha
```

Required account reservations:

```text
DEMO_A = control + D1 shadow observer
DEMO_B = Sleeve B
DEMO_C = Frequency body015
UNASSIGNED = Donchian offline
```

Sleeve B and Frequency may not share a netting account. No engine may adopt another engine's position.

## Future implementation branches

```text
agent/stage10c-observability-repair
agent/shadow-trade-ledger
agent/sleeve-b-demo-execution
agent/stage10c-frequency-body015-demo
agent/stage10d-phase2-data-readiness
```

Each branch must pass its own validation and user checkpoint before the next implementation stage begins.

## Stage sequence after this charter

1. Stage 1 governance and isolation — **CLOSED / PASS**.
2. Repair minimum Stage10C observability defects.
3. Revalidate the exact Sleeve B implementation contract.
4. Design the isolated Frequency body015 implementation.
5. Activate Sleeve B in controlled demo only after its implementation gate.
6. Activate Frequency body015 in controlled demo only after its implementation gate.
7. Build the shadow trade ledger.
8. Continue Stage10D offline through its approved phases.

## Explicit exclusions

Stage 1 did not:

- modify an EA;
- compile or deploy an EA;
- change MT5 inputs;
- create or alter a Worker route;
- migrate Supabase;
- activate Sleeve B;
- activate Frequency body015;
- authorize Donchian execution;
- increase v4.43.0 risk;
- allocate real capital.

## Stage 1 closure gate

```text
machine-readable contract = PASS
contract_id = 57d4efc4cf332d46c4cad9a5
control frozen = PASS
challenger-specific gates preserved = PASS
activation_authorized = false
production_capital_authorized = false
account isolation defined = PASS
identity isolation defined = PASS
risk envelope defined = PASS
future branch boundaries defined = PASS
unit tests and CLI = PASS (9/9)
local worktree hygiene = PASS
CI = PASS
Stage 1 status = CLOSED / PASS
```

Detailed closure evidence is recorded in:

```text
docs/stage10/DEMO_ACCELERATION_STAGE1_CLOSURE.md
```

The next authorized activity is Stage 2 observability repair on its own branch. No Stage 2 implementation is included in this charter closure.
