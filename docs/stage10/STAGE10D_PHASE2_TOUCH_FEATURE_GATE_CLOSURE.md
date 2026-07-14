# Stage10D Phase 2 — Directional Touch Feature Gate Closure

## Status

**CLOSED — PASS**

This checkpoint closes the executable directional EMA21 touch-gap feature subgate for the governed USDJPY H4 dataset. Stage10D Phase 2 remains in progress and no strategy expectancy, EA, Worker, Supabase production, shadow or live authorization is implied.

## Canonical inputs

```text
governed_manifest_id = c4ea6698b0c4858e22fc773a
source_sha256 = b590506b21157ec149064fd8deb3818a6d9039931ba58aab1ee66b33aae38a1e
symbol = USDJPY
timeframe = H4
synthetic = false
```

## Generated artifact

```text
feature_artifact_id = bb709ee3b084c364eb3d503f
feature_version = stage10d-touch-features-v1
row_count = 10161
eligible_row_count = 10101
ineligible_row_count = 60
segment_reset_count = 2
exact_atr = 0.25
soft_atr = 0.50
extended_atr = 1.50
```

The feature artifact is research eligible under the governed H4 manifest. The artifact identity is deterministic for the governed manifest, source checksum, indicator periods, thresholds and excluded timestamps.

## Directional contract validation

The executable contract passed all seven tests:

```text
buy wrong-side candle returns null, not zero
sell wrong-side candle returns null, not zero
geometric contact and 0.25/0.50/1.50 ATR bands are correct
future rows cannot alter past feature values
governed gaps reset EMA/ATR state and require warm-up
source checksum mismatch blocks feature generation
artifact identity and output writer are deterministic
```

## Observed population

```text
buy_directionally_defined_count = 7081
sell_directionally_defined_count = 5768
```

BUY classification counts:

```text
inside_exact = 3471
outside_exact_inside_soft = 727
outside_soft_inside_extended = 1975
outside_extended = 908
unknown = 3080
```

SELL classification counts:

```text
inside_exact = 3421
outside_exact_inside_soft = 525
outside_soft_inside_extended = 1270
outside_extended = 552
unknown = 4393
```

The non-unknown class totals reconcile exactly to the directionally defined counts. `unknown` includes warm-up rows and candles entirely on the wrong side of EMA21 for the corresponding direction.

## Segment and exclusion behavior

```text
segment 0 rows = 7015
segment 1 rows = 1557
segment 2 rows = 1589
```

Indicator resets occurred at the first observed bar after each governed H4 data gap:

```text
2024-07-03 00:00:00
2025-07-03 12:00:00
```

The four absent timestamps remain excluded from analytic windows:

```text
2024-07-02 16:00:00
2024-07-02 20:00:00
2025-07-03 04:00:00
2025-07-03 08:00:00
```

There are 60 `ema_warmup` rows: 20 at the initial dataset segment and 20 after each of the two governed-gap resets. No rows were lost.

## No-look-ahead decision

Features at completed bar `t` use only rows with timestamps less than or equal to `t`. The evaluated completed bar participates in its closing EMA21 and ATR14 values. Appending or changing future bars cannot alter prior feature rows.

## Non-blocking technical debt

Python 3.12 emitted a `DeprecationWarning` for `datetime.utcnow()` while generating the observational `generated_at_utc` field. This warning does not alter feature values, artifact identity, checksums, eligibility or output counts. Replace it with timezone-aware `datetime.now(timezone.utc)` before Phase 2 closure.

## Exit decision

The directional touch feature subgate is **PASS**. The next Phase 2 block is prior-window Donchian instrumentation. It must:

```text
exclude the evaluated bar from every prior window
reset after governed H4 data gaps
require N complete prior bars inside the same segment
remain parameterized by donchian_N
compute BUY and SELL independently
preserve no-look-ahead behavior
produce deterministic run and artifact identity
```

No performance or promotion conclusion is authorized by this checkpoint.
