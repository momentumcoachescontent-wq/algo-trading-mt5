# Stage10D Program Charter — Momentum Continuation Challenger

## Status

Phase 0 foundation document.

No strategy implementation, EA deployment, Worker change, Supabase migration or real-order authorization is included in this phase.

## Purpose

Stage10D is a controlled challenger program designed to test a strategy hypothesis opposite to the Stage10C pullback model:

```text
Stage10C waits for a pullback to EMA21.
Stage10D investigates continuation when the pullback does not occur.
```

The objective is not to force frequency. The objective is to determine whether the market states rejected by Stage10C contain an independent, robust and governable edge.

## Relationship with Stage10C

### Stage10C

- Remains the active USDJPY-first core sleeve.
- Keeps its current entry, risk, management and governance rules.
- Is not modified as part of Stage10D research.
- Continues to provide the baseline and live operational control.

### Stage10D

- Begins as offline research.
- Uses a separate signal identity, run identity and future execution scope.
- Cannot send orders during research or shadow phases.
- Must prove entry value before management changes are considered.
- Must prove complementarity before any micro-live proposal.

## Program structure

### Phase 0 — Alignment and prerequisites

Formalize scope, canonical data sources, taxonomy, dependencies and closure gates.

### Phase 1 — D1 context closure

Diagnose `no_bias_context`, document D1 semantics and define hard-gate versus risk-modulator variants.

### Phase 2 — Data foundation and instrumentation

Build normalized touch, breakout, regime, MFE/MAE and path-quality research inputs.

### Phase 3 — Dead-space audit

Measure what occurred inside Stage10C `no_ema_touch` blocks and decide whether a full challenger backtest is justified.

### Phase 4 — Stage10D-A entry challenger

Test Donchian breakout entry while holding Stage10C management constant.

### Phase 5 — Entry and complementarity gate

Evaluate expectancy, robustness, direction-specific behavior and portfolio contribution.

### Phase 6 — Stage10D-B management challenger

Test Chandelier and other management alternatives only after Stage10D-A passes.

### Phase 7 — Stage10D-C advanced model

Evaluate continuous scoring, persistence and optional M15 confirmation only if prior phases pass.

### Phase 8 — Modular challenger construction

Build a separate, order-disabled Stage10D module using approved governance components.

### Phase 9 — Technical sandbox validation

Validate parity, no look-ahead, duplicate suppression, failure handling and isolation from Stage10C.

### Phase 10 — Shadow forward

Collect forward candidates with order sending disabled.

### Phase 11 — Controlled micro-live

Consider reduced independent risk only after all offline and shadow gates pass.

### Phase 12 — Evaluation and promotion

Promote, extend, revise or retire Stage10D based on portfolio-level evidence.

## Scope absorbed from F5A.6 Pilar C

Stage10D absorbs and extends the following Pilar C work:

- `touch_gap_low_atr` and `touch_gap_high_atr` instrumentation.
- Missed-entry and blocked-opportunity analysis.
- Historical touch frequency by regime.
- MFE/MAE analysis after rejected touch conditions.
- Comparison between pullback and continuation opportunity sets.

There is no separate Pilar C delivery stream after this charter. Existing Pilar C references should be interpreted as Stage10D Phase 2 or Phase 3 work.

## Experiment invariants

1. Change one causal layer at a time.
2. Exclude the signal bar from prior-window Donchian calculations.
3. Prevent repeated signals from the same breakout leg.
4. Report BUY and SELL independently before aggregation.
5. Keep synthetic data out of promotion evidence.
6. Keep `order_send_allowed=false` until the micro-live gate is explicitly approved.
7. Preserve the principle `ENTRY_READY != ORDER_ALLOWED`.
8. Treat missing or ambiguous context as non-executable.
9. Use realistic spread, slippage and intrabar resolution where required.
10. Preserve raw evidence and reproducible run manifests.

## Initial research question

```text
Using the same risk and fixed management as Stage10C, does a prior-window Donchian breakout entry generate positive, robust and complementary expectancy in USDJPY periods where Stage10C records no valid EMA touch?
```

## Stage10D-A minimum comparison

| Variant | Entry | Management | Purpose |
|---|---|---|---|
| A | Stage10C pullback | Current fixed SL/TP | Baseline |
| B | Donchian breakout | Current fixed SL/TP | Isolate entry value |
| C | Stage10C pullback | Chandelier candidate | Isolate management value later |
| D | Donchian breakout | Chandelier candidate | Full challenger later |

Only variants A and B belong to Stage10D-A.

## High-level gates

### Data gate

- Canonical MT5 source documented.
- Required columns and time semantics validated.
- H4 and D1 coverage adequate for the selected historical period.
- M15 coverage adequate for any path-dependent analysis being claimed.
- No silent use of synthetic data.

### Entry gate

- Minimum historical sample defined before optimization.
- Positive net expectancy and PF above the approved threshold.
- Positive out-of-sample and holdout performance.
- Robustness across neighboring Donchian and ADX values.
- Acceptable drawdown and no single-year dependency.
- Results reported separately by direction.

### Complementarity gate

- Low or explainable overlap with Stage10C entries.
- Positive contribution during no-touch regimes.
- Sequential breakout-to-pullback overlap explicitly measured.
- Portfolio combination improves risk-adjusted results or opportunity coverage.

### Shadow gate

- Minimum forward candidate sample reached.
- Offline/live signal parity demonstrated.
- No execution-scope violations.
- Complete telemetry for breakout and block reasons.

## Explicit exclusions

Stage10D Phase 0 does not:

- change Stage10C parameters;
- activate touch_025;
- change TP/SL;
- add break-even;
- activate F5B;
- authorize EURJPY or GBPUSD real trading;
- implement Chandelier trailing;
- create a live Stage10D EA;
- approve real capital allocation.