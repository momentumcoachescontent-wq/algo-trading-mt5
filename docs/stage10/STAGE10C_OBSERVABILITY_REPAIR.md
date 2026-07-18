# Stage10C Observability Repair

## Status

**Stage 2 — CODE VALIDATED / OPERATIONAL CHECKPOINT A PENDING**

This stage repairs Worker and Supabase observability semantics. It does not modify an EA, strategy parameter, signal rule, risk, SL, TP, session, execution policy, or capital authorization. Sleeve B, Frequency body015, and Donchian remain inactive.

Code, contracts, production-dependency security, local validation, and CI are PASS. Migration execution and Worker deployment remain separate operational checkpoints governed by `STAGE10C_OBSERVABILITY_OPERATIONAL_RUNBOOK.md`.

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

Every signal evaluation receives a transparent canonical `signal_eval_id`:

```text
stage10c-sig-v1|symbol|ea_version|strategy_variant|entry_time|direction|entry_price
```

Worker and SQL use the same rules:

- symbol is uppercase;
- version and strategy/phase are lowercase;
- timestamps are UTC with second precision;
- BUY/SELL are normalized to lowercase;
- entry price is rounded to eight decimals and trailing zeros are removed;
- missing values use explicit fallback tokens;
- an explicit EA-provided ID is preserved.

The current Stage10C `eval_time` and `trade_open.open_time` represent the same entry instant, allowing signal and position payloads to derive the same ID even when `trade_open` reaches the Worker first.

For historical rows, the migration generates the same canonical format and links only exact, unique matches by:

```text
symbol
ea_version
direction
eval_time = open_time
entry_price = open_price
```

Ambiguous or missing historical links remain explicit rather than inferred. No foreign key is imposed over incomplete historical evidence.

## Safe close matching

The previous Worker patched all open rows matching `position_id`.

The repaired flow is:

1. Query open candidates by explicit `position_id` and symbol.
2. Prefer an exact `execution_mode` and `strategy_variant` match.
3. Reject any candidate with explicitly conflicting mode or strategy metadata, even when it is the only candidate.
4. Accept one unique legacy candidate only when its missing metadata does not contradict the close payload.
5. Reject ambiguous matches.
6. Patch exactly one row by database `id`.
7. If no compatible candidate exists, persist a fallback close with `link_status=FALLBACK_UNMATCHED_CLOSE`.

A fallback close receives a non-null defensive `open_time` equal to the close timestamp when no original open timestamp is available. This preserves evidence without pretending the link was resolved.

## Persistence changes

Migration:

```text
infra/supabase/migrations/006_stage10c_observability.sql
```

Operational preflight and validation:

```text
infra/supabase/validation/006_stage10c_observability_preflight.sql
infra/supabase/validation/006_stage10c_observability_validation.sql
docs/stage10/STAGE10C_OBSERVABILITY_OPERATIONAL_RUNBOOK.md
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

## Production dependency security

The production framework is pinned exactly:

```text
hono = 4.12.30
```

Validation evidence:

```text
npm test = 17/17 PASS
npm run typecheck = PASS
npm audit --omit=dev = 0 vulnerabilities
```

The full development dependency tree may report advisories from tooling; the deployable production dependency tree must remain at zero known vulnerabilities. CI enforces `npm audit --omit=dev` before semantic tests.

## Operational checkpoint order

This PR has not deployed anything. The mandatory order is:

```text
Checkpoint A
1. Run read-only preflight.
2. Apply 006_stage10c_observability.sql.
3. Run read-only post-migration validation.
4. Reconcile pre/post row counts.
5. Review results.

Checkpoint B — only after Checkpoint A approval
6. Deploy Worker v3.3.0.
7. Send controlled signal/open/close payloads.
8. Validate Supabase decision and linking fields.

Checkpoint C
9. Observe organic H4 events before operational closure.
```

Deploying the Worker before the migration is prohibited because new columns would be rejected by PostgREST.

## Validation commands

```bash
cd infra/worker
npm ci
npm audit --omit=dev
npm test
npm run typecheck

cd ../..
python3 -m unittest tests.test_stage10c_observability_contract -v
```

Expected:

```text
17 Node tests PASS
17 Python contract tests PASS
TypeScript PASS
production audit = 0 vulnerabilities
```

## Exit gate

Stage 2 implementation is ready for operational migration when:

```text
Worker normalization tests = PASS
Worker typecheck = PASS
migration contract tests = PASS
operational SQL contract tests = PASS
valid shadow entry != ERROR = PASS
execution_mode persistence contract = PASS
reason separation contract = PASS
legacy ticket is not misclassified = PASS
Worker/SQL canonical correlation parity = PASS
future signal-position correlation = PASS
explicit candidate metadata mismatch rejected = PASS
single-row close matching = PASS
missing order/deal identity remains explicit = PASS
production dependency audit = 0 vulnerabilities
no EA or strategy change = PASS
local worktree clean = PASS
CI = PASS
```

Operational closure requires migration, deployment, controlled payload validation, and organic H4 evidence. It is not implied by code-level PASS.
