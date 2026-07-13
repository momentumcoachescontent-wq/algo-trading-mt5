# Stage10D Phase 2 — Data Foundation and Instrumentation

## Status

**IN PROGRESS — first vertical slice implemented**

Phase 2 is authorized from `main` merge commit `cbc4a2b`. It remains an offline research phase and does not authorize changes to the active v4.43.0 EA, the v4.43.1 shadow candidate, Worker execution policy, Supabase production schemas or real capital.

## Purpose

Build reproducible and auditable research inputs for the Stage10D dead-space audit and later Donchian challenger analysis.

The Phase 2 data contract must prevent the following from becoming silent assumptions:

- broker/feed identity;
- terminal identity;
- broker-server timezone or offset convention;
- source-file checksum;
- synthetic versus canonical source;
- missing bars, duplicates and malformed OHLC;
- path-quality availability;
- touch and breakout taxonomy.

## First vertical slice

Implemented components:

```text
python/research/stage10d_data_readiness.py
python/pipeline/stage10d_phase2_data_readiness.py
tests/test_stage10d_data_readiness.py
.github/workflows/stage10d-phase2-tests.yml
```

The slice accepts a same-broker MT5 CSV export and produces:

```text
<dataset>_manifest.json
<dataset>_quality.json
<dataset>_normalized.csv
```

### Non-negotiable timestamp behavior

MT5 broker-server timestamps are preserved as wall-clock values. The parser does **not** silently convert them to UTC.

Every run requires explicit metadata:

```text
--broker
--terminal
--server-timezone
```

`--server-timezone` records the broker-server timezone or offset convention. It does not transform the source timestamps.

### Canonical manifest fields

The first manifest version records:

- `data_manifest_id`;
- parser and manifest versions;
- source path, SHA-256 and byte size;
- broker, terminal, symbol and timeframe;
- server-timezone convention;
- optional UTC export timestamp;
- `synthetic=false`;
- row count and coverage range;
- quality status;
- duplicate, OHLC, volume and gap counts.

The manifest identity is deterministic for the source checksum and canonical metadata. The generation timestamp is observational and does not alter `data_manifest_id`.

## Data-quality gate

The first executable gate fails when it detects:

- duplicate bar timestamps;
- invalid OHLC geometry;
- non-positive volume;
- missing weekday bars;
- irregular or non-timeframe-aligned gaps;
- missing required metadata or columns;
- timezone-aware source timestamps that would imply an unapproved conversion path.

Weekend-only missing timestamps are classified as `expected_market_closure` and do not fail the gate.

The taxonomy retains `broker_session_gap`, but the first parser does not infer that category automatically. A broker-session calendar must be explicit before such gaps can be promoted from `missing_export_segment` or `unknown_gap`.

## Supported MT5 layouts

The parser supports:

```text
TIME,OPEN,HIGH,LOW,CLOSE,TICK_VOLUME
```

and standard tab-delimited MT5 layouts with:

```text
<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICK_VOLUME>
```

Column names are normalized case-insensitively. Required price and volume columns remain mandatory.

## Local execution

Example for USDJPY H4:

```bash
python3 python/pipeline/stage10d_phase2_data_readiness.py \
  /path/to/USDJPY_H4.csv \
  --symbol USDJPY \
  --timeframe H4 \
  --broker "<broker-feed-id>" \
  --terminal "mt5-macos-wine" \
  --server-timezone "<broker-server-offset-convention>" \
  --exported-at-utc "2026-07-13T03:00:00Z"
```

Default output directory:

```text
data/processed/stage10d_phase2/
```

Exit codes:

```text
0 = quality PASS
1 = parser, file or metadata error
2 = quality FAIL
```

`--allow-quality-fail` may be used only to persist diagnostic artifacts. It must not be used to promote a failing dataset into performance evidence.

## Required canonical inventory

Phase 2 must next run the gate against same-broker exports for:

| Symbol | Timeframe | Purpose |
|---|---|---|
| USDJPY | H4 | Stage10C blocks, touch, Donchian and regime features |
| USDJPY | D1 | closed-bar D1 context reconstruction |
| USDJPY | M15 | MFE/MAE and intrabar path claims where coverage exists |

The previous inventory checkpoint is not a Phase 2 manifest. New exports must generate fresh checksums, coverage ranges and continuity reports.

## Remaining Phase 2 blocks

1. Execute and close the canonical USDJPY H4/D1/M15 inventory.
2. Add an explicit broker-session calendar or documented exception process.
3. Implement executable directional `touch_gap` fields using the corrected Phase 0 formulas.
4. Implement prior-window Donchian features with the evaluated bar excluded.
5. Add descriptive regime fields for ADX, EMA extension, volatility and D1 alignment.
6. Reconstruct or explicitly mark unavailable MFE/MAE and `path_quality`.
7. Build the normalized opportunity table required by the Phase 3 dead-space audit.

## Closure gate

Phase 2 cannot close until:

```text
H4 canonical manifest = PASS
D1 canonical manifest = PASS
M15 coverage explicitly classified
server-time semantics documented and verified
normalized touch fields validated
prior-window Donchian fields validated with no look-ahead
regime fields reproducible
path-quality policy executable
synthetic rows excluded from promotion evidence
```

No strategy expectancy conclusion belongs to Phase 2. That analysis begins only after the data foundation is closed.
