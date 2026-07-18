# Stage10C Observability Repair

## Status

**Stage 2 — IMPLEMENTED / AWAITING VALIDATION**

This stage repairs Worker and Supabase observability semantics. It does not modify an EA, strategy parameter, signal rule, risk, SL, TP, session, execution policy, or capital authorization. Sleeve B, Frequency body015, and Donchian remain inactive.

## Evidence that triggered the repair

The 12–17 July 2026 review identified four material gaps:

1. A valid v4.43.1 shadow entry emitted `ENTRY_ACCEPTED`, `would_have_traded=true`, and `SCOPE_DENY`, but the summary persisted `decision=ERROR`.
2. The real trade row had `execution_mode=null` despite execution-scope evidence in the payload.
3. `block_reason` mixed signal, governance, and execution-scope causes.
4. `ticket` and `position_id` were treated as interchangeable, obscuring order/deal/position identity.

A final comparison against the raw v4.43.0 payload confirmed:

```text
EXEC log order ticket:        2016949262
trade_open payload ticket:    152340804622
trade_open payload position:  152340804622
```

Therefore the current `trade_open.ticket` is the position identity, not a safe order-ticket source.

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

Entry evidence has precedence over a legacy raw `decision=ERROR` label. Directional actions such as `ENTRY_READY_BUY` and `ENTRY_READY_SELL` satisfy the entry-ready contract. The Worker does not change `order_send_allowed`; it only persists the scope received from the EA.

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

The legacy `ticket` column is preserved exactly as emitted for compatibility. It is not reclassified automatically.

New rules:

- `order_ticket` is populated only from explicit `order_ticket`, `order_id`, or an explicitly declared `ticket_role=ORDER`.
- `deal_ticket` is populated only from explicit `deal_ticket`, `deal_id`, or an explicitly declared `ticket_role=DEAL`.
- `position_id` is populated only from explicit position fields.
- When the payload has `ticket == position_id`, `order_ticket` remains null.
- `link_status` records missing order/deal identities instead of implying a complete link.

The current v4.43.0 position can therefore achieve signal–position correlation, but its order ticket remains unavailable in the webhook payload. Full signal–order–position linking will require a future EA payload to emit `order_ticket` explicitly.

## Signal correlation

Every signal evaluation receives `signal_eval_id`:

- an explicit EA-provided ID is preserved;
- otherwise the Worker derives a deterministic non-cryptographic correlation ID;
- the canonical identity uses symbol, EA version, strategy variant or phase, evaluation/open time, direction, and entry price;
- Stage10C `eval_time` and `trade_open.open_time` represent the same entry instant, allowing both payloads to derive the same ID;
- retries of the same payload resolve to the same ID;
- the migration adds an index but does not impose a foreign key over incomplete historical evidence.

For historical rows, the migration creates legacy IDs and links only exact, unique matches by:

```text
symbol
ea_version
direction
eval_time = open_time
entry_price = open_price
```

Ambiguous or missing historical links remain explicit rather than inferred.

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

- legacy `ticket` is never copied to `order_ticket`, `deal_ticket`, or `position_id`;
- explicit order/deal fields may be recovered from historical `raw_payload`;
- exact unique signal–position matches may be recovered;
- the exact known v4.43.0 USDJPY control may backfill `execution_mode=REAL`;
- missing or ambiguous order/deal links remain null;
- legacy link quality is recorded explicitly.

## Worker behavior

Worker version:

```text
3.3.0-stage10c-observability
```

Signal-evaluation persistence is now required for a successful webhook response. A rejected `signal_evals` insert returns HTTP 500 instead of a misleading HTTP 200, allowing the EA/log audit to detect missing evidence.

Lifecycle events remain best-effort. Retry/spool architecture and changes to the EA payload are outside this stage.

## Deployment order

This PR does not deploy anything. After local validation and explicit approval, the required order is:

```text
1. Apply 006_stage10c_observability.sql.
2. Run schema/backfill validation queries.
3. Deploy Worker v3.3.0.
4. Send controlled signal/open/close test payloads.
5. Validate Supabase decision and linking fields.
6. Observe organic H4 events before operational closure.
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
13 Node tests PASS
11 Python contract tests PASS
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
legacy ticket is not misclassified = PASS
future signal-position correlation = PASS
single-row close matching = PASS
missing order/deal identity remains explicit = PASS
no EA or strategy change = PASS
local worktree clean = PASS
CI = PASS
```

Operational closure requires a later migration/deployment validation checkpoint. It is not implied by code-level PASS.
