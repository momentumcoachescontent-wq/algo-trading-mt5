# Stage10D Phase 1 — v4.43.1 Source Manifest

## Original active-source hashes

| File | SHA-256 |
|---|---|
| `EMA_MTF_v4430_stage10c_usdjpy_first_governance_reset.mq5` | `f4b49710552ef5fc4def01c665975c0041c73bd3d14141888cf73a3b7d49d83b` |
| `MQL5/Include/v30/D1Context.mqh` | `7c907a83c236b193ed8e16bfa40fdbd5384e07e48d2d48aea86113c88d7114c8` |
| `MQL5/Include/v30/H4Signal.mqh` | `ef477d7d4d6f0e07f3813204a3b2475bd7af7d8c4be5e99ed88a3ec822856593` |

The hashes matched the manifest generated from the user's active MetaTrader installation.

## Patched isolated-candidate hashes

| File | SHA-256 |
|---|---|
| `MQL5/Include/v31/D1Context.mqh` | `df5d22b71282f996641279861df8b99285092c3e66c5035e072c17dcec4e7664` |
| `MQL5/Include/v31/H4Signal.mqh` | `911cd26588ccaa2a593937f9bf4b4a2f36b56612c8dc5846348012d279d0d1c5` |
| `MQL5/Experts/Advisors/EMA_MTF_v4431_stage10c_d1_context_integrity.mq5` | `56caf0d648c5df279ad3f0cdeefa10b540c2184d179eb9872ad0887f70b855b8` |

## Distribution package

```text
stage10d_phase1_v4431_package.zip
SHA-256: 2a18aadf59aaaeeb3c6551422e377d62340615fabd55470d6cc23aaddf50ce3e
```

The package contains:

- isolated `v31` D1 and H4 modules;
- new v4.43.1 EA source;
- installation script with backup behavior;
- static contract test;
- source manifest and validation instructions.

## Security

The original source contained a local webhook-secret default. The v4.43.1 candidate intentionally replaces it with an empty input value. No secret is included in the repository manifest or distribution package.

## Required user-side validation

1. Install without overwriting `v30` or v4.43.0.
2. Compile v4.43.1 in MetaEditor.
3. Validate in Strategy Tester or `SHADOW_ONLY`.
4. Return the compile report and resulting MT5 logs.
5. Do not activate real order sending until Phase 1 closure is explicitly confirmed.