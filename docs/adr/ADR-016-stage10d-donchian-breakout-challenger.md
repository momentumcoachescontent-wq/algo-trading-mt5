# ADR-016 — Stage10D Donchian Breakout Continuation Challenger

## Status

Accepted for research foundation.

Stage10D is authorized only for documentation, historical research, sandbox and future shadow validation. This ADR does not authorize real orders, parameter changes in Stage10C, a version bump, or deployment.

## Context

Stage10C v4.43.0 is a conservative USDJPY-first pullback strategy. Its principal entry path requires an EMA21 interaction and subsequent confirmation. During the recent USDJPY regime, the engine evaluated every expected H4 bar but generated no entries, with most blocks concentrated in missing EMA touch and D1 context conflict.

The project therefore needs a competing hypothesis that does not relax Stage10C. The challenger must test whether persistent trend continuation and Donchian breakout can produce an independent edge precisely in the market states rejected by the pullback sleeve.

## Decision

Create Stage10D as a separate challenger program with the following sequence:

1. Stage10D-A — Donchian breakout entry with the existing Stage10C management.
2. Stage10D-B — Management challenger, evaluated only after Stage10D-A passes its entry gate.
3. Stage10D-C — Advanced scoring and optional M15 confirmation, evaluated only after A/B provide evidence.

Stage10D absorbs the research intent previously assigned to Pilar C of F5A.6. Pilar C and Stage10D will not run as duplicate initiatives.

## Core hypothesis

```text
In a strong directional regime, persistent absence of an EMA21 touch may be evidence of continuation rather than an automatic reason to remain out of the market.
```

## Non-negotiable constraints

- Stage10C remains unchanged while Stage10D is researched.
- Stage10D starts offline and cannot send orders.
- Entry and management changes are tested separately.
- Donchian windows exclude the evaluated signal bar.
- D1 logic is not reused blindly until `no_bias_context` is diagnosed.
- Results must be reported separately for BUY and SELL.
- Complementarity against Stage10C is a formal promotion gate.
- Governance, execution scope, sizing and circuit-breaker controls remain at least as restrictive as Stage10C.

## Canonical first experiment

Stage10D-A compares:

```text
Baseline: Stage10C pullback entry + current fixed management
Challenger: prior-window Donchian breakout entry + current fixed management
```

The first experiment does not introduce Chandelier trailing. This isolates the contribution of the entry logic.

## Data decision

The canonical market-data source is MT5 CSV export from the same broker/terminal environment used by the live EA, imported through the existing research pipeline into DuckDB.

Required timeframes:

- H4: primary signal and historical entry research.
- D1: context validation from the same MT5 source.
- M15: path resolution and later Stage10D-C confirmation research.

Synthetic data is prohibited for promotion evidence.

## Consequences

### Positive

- The challenger is independent from the Stage10C pullback mechanism.
- Existing Donchian, ADX, risk and governance infrastructure can be reused after validation.
- The experiment can determine whether the current inactivity is disciplined selectivity or structural signal starvation.
- The design supports causal attribution because entry and exit changes are separated.

### Negative

- Historical D1 and extended M15 coverage must be verified or completed.
- The project must resolve D1 context semantics before a production-equivalent backtest.
- A breakout sleeve can increase false entries and drawdown if regime controls are weak.
- Additional research complexity is accepted only if the challenger demonstrates portfolio complementarity.

## Superseded or absorbed work

- F5A.6 Pilar C touch-gap and missed-opportunity research is absorbed into Stage10D Phases 2 and 3.
- Existing Stage10C touch-gap design remains valid as an observational contract and becomes an input to Stage10D research.

## Promotion principle

Stage10D is not promoted because it trades more frequently. It must demonstrate positive out-of-sample expectancy, robustness, controlled drawdown and measurable complementarity with Stage10C.