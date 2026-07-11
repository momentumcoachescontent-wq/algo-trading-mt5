# Stage10D Phase 1 — D1 Context Closure

## Status

**RESEARCH AND CONTRACT CLOSED — PRODUCTION INTEGRATION BLOCKED**

The D1 semantics, July 2026 root-cause diagnosis, reference contract, audit tooling and regression tests are complete.

The production MQL5 integration cannot be completed in this repository because the active v4.43.0 source modules `H4Signal.mqh` and `D1Context.mqh` are not present. Phase 2 is not authorized until those exact production sources are imported and the integration checklist in this document passes.

## 1. Evidence reviewed

- USDJPY v4.43.0 MT5 logs from July 5–10, 2026.
- Stage10C v4.43.0 orchestration behavior documented in the weekly review.
- Existing repository source and Stage10D Phase 0 contracts.

The audit used the native UTF-16 MT5 logs and reconstructed D1 context transitions before comparing downstream H4 candidate behavior.

## 2. D1 semantics closed

The live logs demonstrate the following discrete-bias behavior:

| Structure | EMA/price components | Discrete bias | Meaning |
|---:|---|---:|---|
| +1 | bullish | +1 | aligned bullish context |
| 0 | bullish | +1 | bullish context without confirmed structure |
| -1 | bullish | 0 | bearish structure conflicts with bullish trend components |
| -1 | bearish | -1 | aligned bearish context |
| 0 | bearish | -1 | bearish context without confirmed structure |
| +1 | bearish | 0 | bullish structure conflicts with bearish trend components |

Therefore the ten `no_bias_context` decisions were not caused by missing D1 data. They corresponded to an explicit structural conflict:

```text
structure = -1
EMA50 rising = true
D1 close above EMA50 = true
H4 close above EMA50 = true
discrete bias = 0
specific reason = d1_bear_structure_conflicts_bull_trend
```

The weighted telemetry remained approximately `+0.400` because it represented different continuous components. It must not be interpreted as the discrete H4 execution bias.

## 3. Root cause

### Finding A — generic reason was semantically incomplete

All ten neutral decisions were logged as:

```text
no_bias_context
```

The data was present and valid. The actual reason was a conflict between bearish D1 structure and bullish EMA/price components.

Required replacement:

```text
d1_bear_structure_conflicts_bull_trend
```

The generic reason may remain only as a top-level category, accompanied by a mandatory specific `bias_d1_block_source`.

### Finding B — two directional candidates were generated after D1 had resolved to neutral

At the D1 transition to July 8:

```text
[D1_DEBUG] ... structure=-1 ... bias=0
```

The next two evaluations still produced BUY candidates in the shadow candidate stage. Only after the EA restart did downstream evaluations begin returning `no_bias_context` before candidate generation.

Automated audit result over the six weekly logs:

| Metric | Result |
|---|---:|
| Files | 6 |
| D1 snapshots | 10 |
| Distinct D1 transitions | 5 |
| Directional candidates while current D1 bias was neutral | **2** |
| Generic `no_bias_context` decisions | **10** |
| D1 formula mismatches in logged snapshots | 0 |

This is evidence of stale or unsynchronized downstream D1 state, most likely a cached bias or separate context instance inside `CH4Signal` that was not refreshed when `D1Context` changed. The exact code-level mechanism cannot be proven without the active `.mqh` files.

## 4. Canonical contract delivered

`python/research/d1_context_contract.py` provides:

- immutable D1 snapshots;
- discrete bias derived from primitive components;
- stable alignment classifications;
- specific reason codes;
- deterministic snapshot identity;
- synchronization checks between D1 and downstream H4 state.

This contract is the reference for research and for the future MQL5 patch. It does not replace the EA implementation.

## 5. Audit tooling delivered

`python/pipeline/audit_d1_context_logs.py`:

- reads UTF-16 and UTF-8 MT5 logs;
- reconstructs D1 transitions;
- validates the logged D1 formula;
- detects H4 bias mismatches;
- detects candidate generation while D1 is neutral;
- maps generic `no_bias_context` events to the specific current reason;
- supports JSON output and `--fail-on-stale` for validation automation.

Example:

```bash
python3 python/pipeline/audit_d1_context_logs.py /path/to/mt5/logs \
  --json-out data/processed/stage10d_phase1_d1_audit.json \
  --fail-on-stale
```

## 6. Production MQL5 integration contract

When `D1Context.mqh` and `H4Signal.mqh` are imported, the patch must satisfy all of the following.

### 6.1 Single snapshot per H4 evaluation

The orchestrator must resolve D1 exactly once for the completed H4 evaluation and create an immutable equivalent of:

```text
D1ContextSnapshot
```

The same snapshot must be passed to:

- H4 signal generation;
- candidate telemetry;
- conservative D1 guards;
- weighted telemetry;
- final decision logging.

No downstream component may retain an independent mutable D1 bias cache across evaluations.

### 6.2 Refresh invariant

Before `CH4Signal::Evaluate()`:

```text
current_snapshot_id == h4_consumed_snapshot_id
```

If not equal:

```text
signal = 0
order_send_allowed = false
block_reason = d1_context_snapshot_mismatch
```

Fail closed; never reuse the previous bias.

### 6.3 Telemetry fields

Each evaluation must expose:

```text
bias_d1_weighted
bias_d1_discrete
bias_d1_structure
bias_d1_has_structure
bias_d1_ema
bias_d1_donchian
bias_d1_alignment
bias_d1_conflict
bias_d1_data_valid
bias_d1_block_source
bias_d1_snapshot_id
h4_consumed_d1_snapshot_id
```

### 6.4 Specific block reasons

Minimum stable reasons:

```text
d1_context_data_invalid
d1_bear_structure_conflicts_bull_trend
d1_bull_structure_conflicts_bear_trend
d1_components_mixed
d1_context_snapshot_mismatch
```

### 6.5 State-transition tests

Production tests must include:

1. `+1 -> 0` transition without EA restart.
2. `0 -> +1` transition without EA restart.
3. `-1 -> 0` transition without EA restart.
4. New D1 bar while six H4 evaluations continue normally.
5. Restart during neutral context.
6. Invalid CopyBuffer/CopyRates result.
7. Weighted positive but discrete neutral conflict.
8. Candidate stage consumes the same snapshot as final decision.

## 7. Tests completed

The pure reference implementation currently passes ten tests covering:

- aligned bullish context;
- bullish context without structure;
- opposite structure neutralization;
- weighted/discrete separation;
- stale H4 bias detection;
- exact block-reason mapping;
- directional candidate generation during neutral context;
- UTF-16 MT5 log parsing.

Validation command:

```bash
python3 -m unittest discover -s tests -v
```

## 8. Phase exit decision

The conceptual ambiguity around `no_bias_context` is closed:

- it was not missing data;
- it was a valid discrete neutralization caused by conflicting D1 structure;
- its telemetry was too generic;
- two evaluations showed stale downstream candidate state around the transition.

However, Phase 1 cannot be marked fully production-complete until the exact active `H4Signal.mqh` and `D1Context.mqh` are placed in the repository and patched against this contract.

### Gate to complete Phase 1 production integration

- Import exact v4.43.0 `H4Signal.mqh`.
- Import exact v4.43.0 `D1Context.mqh`.
- Verify hashes against the files compiled in MT5.
- Implement single-snapshot propagation and fail-closed mismatch handling.
- Compile in MetaEditor with zero errors.
- Replay the July 8 transition and confirm zero stale candidates.
- Run the log auditor with `stale_events=0`.

Until then:

```text
Phase 1 research/contract = PASS
Phase 1 production integration = BLOCKED_MISSING_SOURCE
Phase 2 authorization = DENIED
```
