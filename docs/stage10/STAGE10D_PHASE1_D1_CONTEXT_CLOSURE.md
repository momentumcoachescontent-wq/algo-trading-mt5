# Stage10D Phase 1 — D1 Context Closure

## Status

**IMPLEMENTED — PENDING METAEDITOR COMPILE AND SHADOW REPLAY**

The exact active v4.43.0 sources were recovered and verified against the supplied SHA-256 manifest. The code-level root cause is now confirmed and a v4.43.1 isolated candidate has been produced.

Phase 2 remains blocked until v4.43.1 compiles and passes the Phase 1 shadow/replay gate.

## 1. Sources verified

Original files recovered from the active MT5 installation:

| File | SHA-256 |
|---|---|
| `EMA_MTF_v4430_stage10c_usdjpy_first_governance_reset.mq5` | `f4b49710552ef5fc4def01c665975c0041c73bd3d14141888cf73a3b7d49d83b` |
| `D1Context.mqh` | `7c907a83c236b193ed8e16bfa40fdbd5384e07e48d2d48aea86113c88d7114c8` |
| `H4Signal.mqh` | `ef477d7d4d6f0e07f3813204a3b2475bd7af7d8c4be5e99ed88a3ec822856593` |

The package manifest matched all three files.

## 2. Confirmed D1 semantics

The ten historical `no_bias_context` decisions were valid discrete neutralizations:

```text
structure = -1
EMA50 rising = true
D1 close above EMA50 = true
H4 close above EMA50 = true
bias_d1_weighted ≈ +0.400
bias_d1_discrete = 0
specific reason = d1_bear_structure_conflicts_bull_trend
```

The weighted C1 score and the discrete execution bias represent different contracts. A positive weighted score does not override a neutral discrete bias.

## 3. Corrected root cause

The first Phase 1 draft described the two BUY candidates during neutral D1 as possible stale cached state. Inspection of the exact source disproved that hypothesis.

### Actual defect

`CH4Signal::Evaluate()` calculated `pattern_bull` and `pattern_bear` independently of `bias_d1`:

```text
raw H4 pattern -> h4_signal
```

The `bias_d1` argument was used only to select a diagnostic fail reason when no H4 pattern existed. Therefore a valid bullish H4 pattern could return `+1` while the discrete D1 bias was `0` or `-1`.

This contradicted the orchestration comments and intended Stage10C architecture, which stated that H4 used the legacy D1 bias.

### Why behavior appeared to change after restart

The restart correlation was incidental. Candidate generation depended on whether the H4 two-candle pattern was present, not on a stale D1 cache. Once the H4 pattern disappeared, evaluations returned `no_bias_context`.

The correct classification of the two events is:

```text
raw_candidate_while_d1_neutral
```

They are useful research candidates, but they must not become an executable H4 signal.

## 4. v4.43.1 implementation

The candidate is isolated from the active modules:

```text
MQL5/Include/v31/D1Context.mqh
MQL5/Include/v31/H4Signal.mqh
MQL5/Experts/Advisors/EMA_MTF_v4431_stage10c_d1_context_integrity.mq5
```

The active `v30` modules and v4.43.0 EA are not overwritten.

### H4 raw-versus-filtered contract

`H4Signal` now preserves:

```text
LastRawSignalDirection
LastSignalDirection
LastConsumedBiasD1
LastD1ContextReason
LastD1SnapshotId
```

Promotion rules:

| Raw H4 | Discrete D1 | Filtered H4 | Reason |
|---:|---:|---:|---|
| +1 | +1 | +1 | `signal_ok` |
| -1 | -1 | -1 | `signal_ok` |
| ±1 | 0 | 0 | `d1_neutral_blocks_h4_signal` |
| +1 | -1 | 0 | `d1_bias_blocks_opposite_h4_signal` |
| -1 | +1 | 0 | `d1_bias_blocks_opposite_h4_signal` |

A raw candidate remains observable for Stage10D research, but only the filtered signal can enter the Stage10C decision waterfall.

### D1 snapshot integrity

`D1Context` now exposes:

```text
IsDataValid()
GetContextReason()
GetClosedD1Bar()
GetSnapshotRevision()
GetSnapshotId()
```

The EA resolves one D1 snapshot per H4 evaluation and passes the same bias, reason and snapshot identity to H4.

Fail-closed invariant:

```text
bias_d1_snapshot_id == h4_consumed_d1_snapshot_id
```

If false:

```text
h4_signal = 0
block_reason = d1_context_snapshot_mismatch
order_send_allowed = false
```

### Specific D1 reasons

The implementation distinguishes:

```text
d1_bull_structure_price_aligned
d1_bear_structure_price_aligned
d1_neutral_structure_bull_trend
d1_neutral_structure_bear_trend
d1_bear_structure_conflicts_bull_trend
d1_bull_structure_conflicts_bear_trend
d1_context_neutral
d1_context_values_invalid
```

### Telemetry added

Each edge payload now exposes:

```text
bias_d1_weighted
bias_d1_discrete
bias_d1_structure
bias_d1_data_valid
bias_d1_context_reason
bias_d1_snapshot_id
h4_consumed_d1_snapshot_id
d1_snapshot_match
h4_raw_signal
h4_signal
```

`[D1_CONTEXT_SNAPSHOT]` logs the exact snapshot consumed by H4.

## 5. Security and isolation

- The v4.43.1 source contains no committed webhook secret.
- `InpWebhookSecret` defaults to an empty string.
- The EA defaults remain `SHADOW_ONLY` and `AllowRealTrading=false`.
- No Stage10C risk, SL, TP, touch, compression or governance parameter was changed.
- The implementation corrects signal-direction integrity only.

## 6. Validation completed

Twelve local contract tests passed:

- neutral D1 blocks raw BUY;
- neutral D1 blocks raw SELL;
- opposite D1 blocks the candidate;
- aligned candidates are promoted;
- snapshot mismatch fails closed;
- raw and filtered directions are both preserved;
- one snapshot is consumed by the EA and H4;
- specific D1 reasons are exposed;
- payload contains the new integrity fields;
- the repository candidate contains no webhook secret;
- the EA uses isolated `v31` modules;
- patched module delimiter balance is valid.

The MT5 auditor has also been corrected: a raw candidate during neutral D1 is no longer labeled stale state. It is an ungated research candidate and becomes an integrity defect only if the filtered H4 signal remains nonzero.

## 7. Patched candidate hashes

| File | SHA-256 |
|---|---|
| `v31/D1Context.mqh` | `df5d22b71282f996641279861df8b99285092c3e66c5035e072c17dcec4e7664` |
| `v31/H4Signal.mqh` | `911cd26588ccaa2a593937f9bf4b4a2f36b56612c8dc5846348012d279d0d1c5` |
| `EMA_MTF_v4431_stage10c_d1_context_integrity.mq5` | `56caf0d648c5df279ad3f0cdeefa10b540c2184d179eb9872ad0887f70b855b8` |

## 8. Remaining compile and shadow gate

Phase 1 closes only after the user validates in MetaEditor and MT5:

1. Compile v4.43.1 with zero errors.
2. Do not replace the running v4.43.0 EA during compile testing.
3. Run v4.43.1 in Strategy Tester or `SHADOW_ONLY`.
4. Confirm `bias_d1_discrete=0` never produces filtered `h4_signal != 0`.
5. Confirm opposite D1/H4 directions never produce `ENTRY_READY`.
6. Confirm `d1_snapshot_match=true` on every evaluation.
7. Confirm no real order is sent.
8. Run the auditor with `--fail-on-integrity` and obtain zero integrity events.

Current gate:

```text
Phase 1 diagnosis = PASS
Phase 1 implementation = PASS
Phase 1 static tests = PASS
Phase 1 MetaEditor compile = PENDING USER VALIDATION
Phase 1 shadow/replay = PENDING USER VALIDATION
Phase 2 authorization = DENIED
```