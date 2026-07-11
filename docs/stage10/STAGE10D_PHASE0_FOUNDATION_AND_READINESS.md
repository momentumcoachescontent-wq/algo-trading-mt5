# Stage10D Phase 0 — Foundation and Readiness Closure

## Status

**CLOSED — PASS**

Phase 0 closes the alignment and prerequisite decisions required before Stage10D technical research begins.

This closure authorizes progression only to **Phase 1 — D1 Context Closure** after review. It does not authorize strategy implementation, backtest optimization, EA deployment, Worker changes, Supabase changes or real execution.

## 1. Decisions closed in Phase 0

| Decision | Resolution |
|---|---|
| Relationship with Stage10C | Stage10C remains unchanged and acts as the core baseline |
| Relationship with F5A.6 Pilar C | Stage10D absorbs Pilar C; no parallel duplicate initiative |
| First challenger | Stage10D-A Donchian breakout entry |
| First management | Reuse current fixed management to isolate entry value |
| Chandelier research | Deferred to Stage10D-B after Stage10D-A passes |
| D1 reuse | Blocked until `no_bias_context` is diagnosed |
| Historical source | MT5 CSV exports from the same broker/terminal environment |
| Research store | Existing DuckDB research pipeline |
| Synthetic data | Allowed only for software tests; prohibited for performance evidence |
| Direction reporting | BUY and SELL evaluated independently before aggregation |
| Execution | Offline/shadow only until explicit future gate |

## 2. Canonical data-source contract

### 2.1 Source of truth

The canonical source for Stage10D market data is:

```text
MT5 broker history export -> CSV -> existing extract --from-csv pipeline -> DuckDB
```

The current research CLI already supports CSV ingestion through:

```text
python -m python.pipeline.run_backtest extract \
  --symbol USDJPY \
  --timeframe <H4|D1|M15> \
  --from-csv <path>
```

Performance evidence must be reproducible from raw exports and a run manifest. Supabase `signal_evals` is an operational and observational source, not a substitute for historical OHLC required to calculate alternative Donchian windows.

### 2.2 Required timeframes

#### H4 — mandatory for Stage10D-A

Used for:

- prior-window Donchian breakout calculations;
- EMA21 distance and persistence;
- ADX and ATR regime features;
- fixed-management simulation;
- Stage10C versus Stage10D opportunity comparison.

#### D1 — mandatory before production-equivalent Stage10D-A conclusions

Used for:

- D1 bias reconstruction;
- comparison with the live EA context;
- hard-gate and risk-modulator variants;
- diagnosis of context conflict.

D1 must come from the same MT5 broker history and server-time convention as H4. UTC resampling of H4 is not accepted unless server-day alignment has been explicitly proven equivalent.

#### M15 — mandatory only for path-dependent claims and Stage10D-C

Used for:

- MFE/MAE and intrabar order resolution;
- ambiguity resolution when SL and TP may occur inside one H4 candle;
- future breakout-retest confirmation;
- shadow outcome reconstruction.

Limited M15 history does not block the first H4 opportunity-frequency audit, but it blocks claims that require full intrabar path accuracy.

### 2.3 Current known inventory

The previously validated local MT5 export inventory contains:

| Timeframe | Symbol | Approximate rows | Range | Readiness |
|---|---|---:|---|---|
| H4 | USDJPY | 10,034 | 2020-01-02 to 2026-06-12 | Adequate foundation |
| M15 | USDJPY | 2,893 | 2026-05-01 to 2026-06-12 | Forward/recent path only |
| D1 | USDJPY | Not yet registered in the inventory | To be verified from MT5 export | Required before historical D1 gate conclusions |

These counts are an inventory checkpoint, not a permanent golden snapshot. Phase 2 must generate a machine-readable manifest and continuity report before historical experiments are promoted.

### 2.4 Time semantics

Every imported dataset must record:

- source terminal/broker;
- symbol;
- timeframe;
- server timezone or offset convention;
- export timestamp;
- first and last bar time;
- row count;
- duplicate count;
- gap count;
- checksum;
- parser version.

Any timezone ambiguity is a data-quality failure for D1 context research.

## 3. Data-quality policy

### 3.1 Required OHLC checks

- `time` strictly increasing after deduplication;
- no duplicate `(symbol, timeframe, time)` keys;
- `high >= max(open, close)`;
- `low <= min(open, close)`;
- `high >= low`;
- positive volume where the source provides it;
- expected timeframe spacing, with broker closures classified separately from unexplained gaps;
- no silent timezone conversion;
- no mixed broker feeds inside one run.

### 3.2 Gap treatment

Gaps are classified as:

```text
expected_market_closure
broker_session_gap
missing_export_segment
unknown_gap
```

`unknown_gap` and `missing_export_segment` invalidate path-dependent results for the affected interval until repaired or explicitly excluded.

### 3.3 Synthetic-data rule

Synthetic OHLC may be used to test code paths, schemas and deterministic calculations. It may not be used to:

- pass a performance gate;
- select Donchian N;
- select ADX thresholds;
- support expectancy, PF or drawdown claims;
- justify shadow or live promotion.

## 4. `path_quality='tracker_missing'` resolution

`tracker_missing` is retained as a cross-cutting data-quality debt, but its treatment is now explicit.

### Allowed use

Rows with `tracker_missing` may be used for:

- signal frequency;
- block-reason counts;
- touch and breakout classification when OHLC is independently available;
- candidate overlap analysis.

### Prohibited use

Rows with `tracker_missing` may not be used as authoritative evidence for:

- MFE/MAE;
- management comparison;
- trailing-stop performance;
- intrabar path quality;
- capture ratio;
- SL/TP ordering when both levels are reachable inside the same H4 candle.

### Closure path

The debt is assigned to Stage10D Phase 2, where path metrics must be reconstructed from canonical M15 data or marked unavailable. No default value may be substituted for missing path evidence.

## 5. Unified research taxonomy

### 5.1 Evaluation bar

```text
eval_bar_time = open time of the completed H4 bar being evaluated
```

All features and prior windows must be based only on information available at or before the close of that bar.

### 5.2 EMA touch taxonomy

A touch is directional and based on the completed H4 candle range, not only the close.

#### BUY-side geometric gap

```text
touch_gap_buy_price = max(0, low - ema21)
touch_gap_buy_atr = touch_gap_buy_price / atr14
```

#### SELL-side geometric gap

```text
touch_gap_sell_price = max(0, ema21 - high)
touch_gap_sell_atr = touch_gap_sell_price / atr14
```

#### Classification

```text
inside_exact
outside_exact_inside_soft
outside_soft_inside_extended
outside_extended
unknown
```

The thresholds are configuration metadata and must not be inferred from labels alone.

Separate fields are required for:

- geometric intrabar contact;
- configured touch-zone pass;
- direction-specific touch;
- final Stage10C touch gate result.

This prevents `touch_bull`, `touch_zone` and accepted pattern touch from being treated as synonyms.

### 5.3 Donchian breakout taxonomy

For a BUY signal at bar `t`:

```text
prior_donchian_high_N(t) = max(high[t-N], ..., high[t-1])
breakout_buy(t) = close[t] > prior_donchian_high_N(t)
```

For a SELL signal at bar `t`:

```text
prior_donchian_low_N(t) = min(low[t-N], ..., low[t-1])
breakout_sell(t) = close[t] < prior_donchian_low_N(t)
```

The evaluated bar is always excluded from the prior window.

Optional research measures may include:

```text
breakout_margin_atr
close_location_value
range_expansion_atr
bars_since_previous_breakout
```

They are descriptive until a later phase explicitly promotes them into a rule.

### 5.4 Breakout leg

A breakout leg is a unique directional market movement, not every consecutive closing bar outside the channel.

Required identity:

```text
breakout_leg_id = symbol + direction + leg_start_time + donchian_N
```

A new leg cannot begin until a reset condition is met. Reset definitions will be tested in Phase 3, but duplicate consecutive signals from the same leg must never be counted as independent opportunities by default.

### 5.5 D1 context taxonomy

D1 context must expose separate values:

```text
bias_d1_weighted
bias_d1_discrete
bias_d1_structure
bias_d1_ema
bias_d1_donchian
bias_d1_conflict
bias_d1_data_valid
bias_d1_block_source
```

`no_bias_context` is not an acceptable final research explanation unless `bias_d1_block_source` identifies the exact failed condition.

### 5.6 Regime taxonomy

Initial regime labels are descriptive:

#### Trend strength

```text
weak
moderate
strong
very_strong
```

Derived from ADX bands recorded in the run configuration.

#### EMA extension

```text
near_ema
continuation_zone
extended
extreme_extension
```

Derived from absolute distance to EMA21 in ATR units.

#### D1 alignment

```text
aligned
partially_aligned
conflict
strongly_opposed
invalid
```

#### Volatility state

```text
compressed
normal
expanded
```

No regime label becomes a hard gate during Phase 0.

## 6. Research identity and reproducibility

Every Stage10D run must eventually include:

```text
run_id
strategy_family = stage10d
strategy_variant
symbol
direction_scope
data_manifest_id
code_commit_sha
config_hash
donchian_N
adx_threshold
extension_limit_atr
d1_mode
management_mode
cost_model
sample_start
sample_end
```

A result without a data manifest and configuration hash is exploratory only and cannot pass a promotion gate.

## 7. Priority and dependency resolution

### Highest operational priority

Stage10C uptime, execution safety and telemetry remain protected. Stage10D research cannot introduce changes into the live Stage10C path.

### Stage10D immediate priority

The next authorized work item is Phase 1:

```text
Diagnose and close D1 context semantics before reusing the D1 gate.
```

### Consolidated technical debt

The following work is absorbed into Stage10D rather than maintained as separate initiatives:

- Pilar C touch-gap instrumentation;
- historical `backtests` population needed by challenger research;
- path-quality reconstruction for Stage10D comparisons;
- blocked-opportunity analysis.

### Deferred work

- Chandelier implementation;
- M15 entry confirmation;
- real EA module;
- Worker execution policy for Stage10D;
- Supabase production schema changes;
- dashboard production changes.

## 8. Phase 0 closure checklist

| Requirement | Status | Evidence/decision |
|---|---|---|
| Stage10D incorporated into the master program | PASS | Program charter and ADR-016 |
| Scope and relationship with Stage10C defined | PASS | Stage10C unchanged; Stage10D separate |
| Pilar C relationship resolved | PASS | Absorbed into Stage10D Phases 2–3 |
| Canonical OHLC source selected | PASS | Same-broker MT5 CSV exports |
| Historical storage path selected | PASS | Existing DuckDB pipeline |
| H4 inventory documented | PASS | USDJPY 2020–2026 foundation available |
| M15 limitation documented | PASS | Recent path coverage only |
| D1 source requirement defined | PASS | Same-broker D1 export required |
| `tracker_missing` policy defined | PASS | Frequency allowed; path evidence prohibited |
| Touch taxonomy defined | PASS | Geometry, configured zone and gate separated |
| Breakout taxonomy defined | PASS | Prior window excludes current bar |
| Duplicate breakout policy defined | PASS | `breakout_leg_id` required |
| Regime taxonomy defined | PASS | Descriptive initial labels |
| Phase 1 entry gate defined | PASS | D1 diagnosis only; no strategy development |

## 9. Exit decision

Phase 0 is closed.

The program may proceed to Phase 1 only after this foundation package is reviewed. Phase 1 must remain limited to `H4Signal.mqh`, `D1Context.mqh`, associated tests/telemetry semantics and the exact cause of `no_bias_context`.

No Donchian strategy code is authorized until Phase 1 is closed.