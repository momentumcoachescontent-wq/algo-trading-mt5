# Stage10C Observability Repair

## Status

**Stage 2 — IMPLEMENTED / AWAITING VALIDATION**

This stage repairs Worker and Supabase observability semantics. It does not modify an EA, strategy parameter, signal rule, risk, SL, TP, session, execution policy, or capital authorization. Sleeve B, Frequency body015, and Donchian remain inactive.

## Evidence that triggered the repair

The 12–17 July 2026 review identified four material gaps:

1. A valid v4.43.1 shadow entry emitted `ENTRY_ACCEPTED`, `would_have_traded=true`, and `SCOPE_DENY`, but the summary persisted `decision=ERROR`.
2. The real trade row had `execution_mode=null` despite execution-scope evidence in the payload.
3. `block_reason` mixed signal, governance, and execution-scope causes.
4. `ticket` and `position_id` were treated as interchangeable, obscuring order/deal/position linking.

## Correct semantic contract

### Decision

```text
valid ENTRY_READY + REAL + order_send_allowed=true
    -> ENTRY_READY_REAL_ALLOWED

valid ENTRY_READY + SHADOW_ONLY/order_send_allowed=false
    -> ENTRY_READY_SHADOW_ONLY_BLOCKED

technical block
    -> BLOCKED_BY_TECHNICAL_GUARD

governance block
    -> BLOCKED_BY_GOVERNANCE_GUARD

execution-scope block without a valid entry
    -> BLOCKED_BY_EXECUTION_SCOPE

actual processing error only
    -> ERROR
```

Entry evidence has precedence over a legacy raw `decision=ERROR` label. The Worker does not change `order_send_allowed`; it only persists the scope received from the EA.

### Reasons

The persisted ledger separates:

```text
primary_signal_reason
    technical signal or pattern reason

governance_guard_reason
    position/session/Friday/circuit/governance reason

execution_denied_reason
    execution_scope or final scope denial reason
```

The original `block_reason`, `action`, and `raw_payload` are preserved.

### Trade identity

```text
order_ticket != deal_ticket != position_id
```

Legacy `ticket` remains for compatibility, but it is event-specific:

```text
trade_open  -> ticket mirrors order_ticket
trade_close -> ticket mirrors deal_ticket
```

A legacy `ticket` is never copied into `position_id`.

## Signal correlation

Every signal evaluation receives `signal_eval_id`:

- an explicit EA-provided ID is preserved;
- otherwise the Worker derives a deterministic non-cryptographic correlation ID from symbol, EA version, strategy variant, evaluated H4/evaluation time, direction, and entry price;
- retries of the same payload resolve to the same ID;
- the migration adds an index but does not impose a foreign key over incomplete historical evidence.

Trades persist `signal_eval_id` only when supplied or safely available. Missing historical links remain null instead of being inferred.

## Safe close matching

The previous Worker patched all open rows matching `position_id`.

The repaired flow is:

1. Query open candidates by explicit `position_id` and symbol.
2. Prefer an exact `execution_mode` and `strategy_variant` match.
3. Accept one unique legacy candidate when no exact metadata exists.
4. Reject ambiguous matches.
5. Patch exactly one row by database `id`.
6. If no candidate exists, persist a fallback close with `link_status=FALLBACK_UNMATCHED_CLOSE`.

A fallback close receives a non-null defensive `open_time` equal to the close timestamp when no original open timestamp is available. This preserves evidence without pretending the link was resolved.

## Persistence changes

Migration:

```text
infra/supabase/migrations/006_stage10c_observability.sql
```

New or normalized fields include:

### `signal_evals`

```text
signal_eval_id
decision
technical_signal_status
execution_mode
order_send_allowed
would_have_traded
primary_signal_reason
governance_guard_reason
execution_denied_reason
policy_name
strategy_variant
guard_version
magic_number
boot_id
bar_h4
```

### `trades`

```text
order_ticket
deal_ticket
position_id
signal_eval_id
execution_mode
strategy_variant
guard_version
magic_number
boot_id
link_status
raw_payload
```

Historical backfill is intentionally conservative:

- open `ticket` backfills only `order_ticket`;
- close `ticket` backfills only `deal_ticket`;
- the exact known v4.43.0 USDJPY control may backfill `execution_mode=REAL`;
- no historical signal-to-trade link is invented;
- legacy link quality is recorded explicitly.

## Worker behavior

Worker version:

```text
3.3.0-stage10c-observability
```

Signal-evaluation persistence is now required for a successful webhook response. A rejected `signal_evals` insert returns HTTP 500 instead of a misleading HTTP 200, allowing the EA/log audit to detect missing evidence.

Lifecycle events remain best-effort. Retry/spool architecture is outside this stage.

## Deployment order

This PR does not deploy anything. After local validation and explicit approval, the required order is:

```text
1. Apply 006_stage10c_observability.sql.
2. Run schema/backfill validation queries.
3. Deploy Worker v3.3.0.
4. Send controlled signal/open/close test payloads.
5. Validate Supabase linking and semantic decisions.
6. Observe organic H4 events before closing Stage 2.
```

Deploying the Worker before the migration is prohibited because new columns would be rejected by PostgREST.

## Validation commands

```bash
cd infra/worker
npm ci
npm test
npm run typecheck

cd ../..
python3 -m unittest tests.test_stage10c_observability_contract -v
```

Expected:

```text
11 Node tests PASS
9 Python contract tests PASS
TypeScript PASS
```

## Exit gate

Stage 2 implementation is ready for operational deployment only when:

```text
Worker normalization tests = PASS
Worker typecheck = PASS
migration contract tests = PASS
valid shadow entry != ERROR = PASS
execution_mode persistence contract = PASS
reason separation contract = PASS
order/deal/position separation = PASS
single-row close matching = PASS
no EA or strategy change = PASS
local worktree clean = PASS
CI = PASS
```

Operational closure requires a later migration/deployment validation checkpoint. It is not implied by code-level PASS.
