# Stage10D Phase 2 — Directional Touch Features

## Status

**IN PROGRESS — executable H4 touch-gap slice implemented**

This slice remains offline research only. It does not alter Stage10C, the active EA, Worker policy, Supabase production schemas, order authorization or capital.

## Inputs

The builder requires:

```text
exports/USDJPY_H4.csv
an H4 governed manifest with research_eligible=true
```

The source CSV checksum must match the governed manifest exactly.

## Closed-bar and no-look-ahead contract

For evaluated H4 bar `t`:

```text
eval_bar_time = open time of the completed H4 bar
```

EMA21, ATR14 and directional touch fields at `t` use only rows with `time <= t`. Future bars are never read when producing features for an earlier bar.

### Indicator definitions

- EMA21 uses the standard recursive EMA with `alpha = 2 / (21 + 1)`.
- The first EMA value in each valid segment is seeded with the SMA of the first 21 closes.
- ATR14 uses Wilder smoothing.
- The first ATR value requires 14 true ranges, and therefore 15 bars in a segment because each true range after the first bar needs a previous close.
- The evaluated bar is completed and may contribute its close/range to its own closed-bar EMA21 and ATR14 values.

## Governed-gap behavior

Confirmed session closures do not create synthetic bars and do not reset indicators.

A governed data gap does reset EMA/ATR state. The first source bar after a gap starts a new segment. Rows remain ineligible until both indicators complete warm-up inside the new segment.

For the canonical USDJPY H4 dataset, the governed missing timestamps are:

```text
2024-07-02 16:00:00
2024-07-02 20:00:00
2025-07-03 04:00:00
2025-07-03 08:00:00
```

No interpolation or alternate-feed reconstruction is allowed.

## Directional geometry

### BUY

```text
touch_gap_buy_price = high >= ema21 ? max(0, low - ema21) : null
touch_gap_buy_atr   = touch_gap_buy_price is not null ? touch_gap_buy_price / atr14 : null
```

### SELL

```text
touch_gap_sell_price = low <= ema21 ? max(0, ema21 - high) : null
touch_gap_sell_atr   = touch_gap_sell_price is not null ? touch_gap_sell_price / atr14 : null
```

A candle entirely on the wrong side of EMA21 for a direction produces `null`, not zero.

## Threshold metadata

```text
exact_atr    = 0.25
soft_atr     = 0.50
extended_atr = 1.50
```

Classifications:

```text
inside_exact                  gap <= 0.25 ATR
outside_exact_inside_soft     0.25 < gap <= 0.50 ATR
outside_soft_inside_extended  0.50 < gap <= 1.50 ATR
outside_extended              gap > 1.50 ATR
unknown                       direction undefined or indicators invalid
```

Separate fields are emitted for geometric contact and exact/soft/extended configured zones. These are descriptive Phase 2 fields and do not change the Stage10C entry gate.

## Outputs

```text
<artifact>_touch_manifest.json
<artifact>_touch_features.csv
```

The feature manifest records:

- governed manifest identity;
- source checksum;
- periods and thresholds;
- row and eligibility counts;
- exact governed missing timestamps;
- segment reset count;
- no-look-ahead contract;
- `synthetic=false`.

## Local execution

```bash
python3 python/pipeline/build_stage10d_phase2_touch_features.py \
  exports/USDJPY_H4.csv \
  --governed-manifest <H4-governed-manifest.json> \
  --output-dir data/processed/stage10d_phase2/touch_features
```

## Validation gate

The slice must prove:

```text
wrong-side BUY/SELL -> null, never zero
exact geometric contact -> zero gap
0.25/0.50/1.50 classifications deterministic
future rows cannot alter past features
governed gaps reset indicator segments
checksum mismatch blocks execution
artifact identity deterministic
```

This slice does not yet implement Donchian, D1 alignment, regime labels, MFE/MAE or expectancy analysis.
