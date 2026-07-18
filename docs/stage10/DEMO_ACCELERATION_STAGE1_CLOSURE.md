# Demo Acceleration Stage 1 Closure

## Status

**CLOSED / PASS — governance, identity, risk, and isolation contract**

Stage 1 is complete. It establishes the machine-readable governance contract for the Demo Acceleration program and validates that no new execution path is authorized.

## Closure evidence

### Canonical contract

```text
path: configs/demo_acceleration/demo_acceleration_v1.json
contract_id: 57d4efc4cf332d46c4cad9a5
program_version: demo-acceleration-governance-v1
program_status: GOVERNANCE_ONLY
environment: DEMO
engine_count: 5
planned_execution_count: 2
activation_authorized: false
production_capital_authorized: false
```

### Local validation

Executed on the user's local checkout:

```text
python3 python/pipeline/validate_demo_acceleration_contract.py \
  configs/demo_acceleration/demo_acceleration_v1.json

status: PASS_GOVERNANCE_CONTRACT
errors: []
```

Regression result:

```text
python3 -m unittest tests.test_demo_acceleration_contract -v
Ran 9 tests in 0.104s
OK
```

### GitHub Actions

```text
Demo Acceleration Governance Tests: PASS
Stage10D Phase 1 regression: PASS
```

### Worktree and data hygiene

```text
git status --short: clean
exports/: ignored by .gitignore
exports/USDJPY_D1.csv: preserved locally
exports/USDJPY_H4.csv: preserved locally
exports/USDJPY_M15.csv: preserved locally
```

The local canonical market-data exports remain available for research but cannot be committed accidentally.

## Engine state at closure

| Engine | Account | Mode | Risk | Activation |
|---|---|---|---:|---|
| v4.43.0 control | DEMO_A | DEMO_EXECUTION_CONTROL | 0.25% | Existing only |
| v4.43.1 D1 integrity | DEMO_A | SHADOW_ONLY | 0% | Existing only |
| Sleeve B SELL touch_025 | DEMO_B | DEMO_EXPERIMENTAL_PLANNED | 0.50% to 0.75% | Not authorized |
| Frequency body015 | DEMO_C | DEMO_EXPERIMENTAL_PLANNED | 0.50% to 0.75% | Not authorized |
| Stage10D Donchian | Unassigned | OFFLINE_ONLY | 0% | Blocked from execution |

## Preserved gates

### Sleeve B Stage10A

```text
minimum forward window = 16 weeks
minimum trades = 30
median_r > 0
top3_share < 40%
```

### Stage10D Donchian

```text
minimum trades = 80
profit factor > 1.15
positive out-of-sample required
all four approved mandatory conditions required
```

The generic Frequency checkpoints do not replace either inherited gate.

## Safety findings

The Stage 1 validator proved that:

- v4.43.0 risk and causal parameters remain frozen;
- v4.43.1 remains order-disabled;
- Sleeve B and Frequency cannot be activated in this stage;
- Donchian remains offline;
- all strategy variants and Magic numbers are unique;
- experimental account reservations remain isolated;
- real capital is not authorized;
- changing inherited gate values fails validation;
- changing more than `body_c1_min` in Frequency fails validation.

## Explicitly unchanged

Stage 1 did not:

- modify or compile an EA;
- change MT5 inputs;
- activate Sleeve B;
- activate Frequency body015;
- authorize Donchian execution;
- alter Worker or Supabase production behavior;
- change v4.43.0 risk or parameters;
- allocate real capital.

## Next authorized stage

The next program stage is **Stage 2 — minimum Stage10C observability repair**.

Its scope is limited to making signal, guard, execution identity, and persistence semantics auditable before any new challenger is activated. Stage 2 must use its own branch and validation checkpoint.

No Stage 2 implementation is included in this closure.
