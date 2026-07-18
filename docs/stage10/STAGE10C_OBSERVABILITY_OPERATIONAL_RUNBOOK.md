# Stage10C Observability Operational Runbook

## Status

**CODE VALIDATED — MIGRATION CHECKPOINT NOT YET EXECUTED**

This runbook applies and validates Supabase migration `006_stage10c_observability.sql` before Worker v3.3.0 is deployed.

The checkpoint is deliberately split:

```text
Checkpoint A = preflight + migration + post-migration validation
Checkpoint B = Worker deployment + controlled payload validation
Checkpoint C = organic H4 evidence and operational closure
```

Do not begin Checkpoint B until Checkpoint A is reviewed and approved.

## Safety boundary

This checkpoint does not:

- modify any MQL5 source;
- change strategy, risk, SL, TP, sessions, or execution policy;
- activate Sleeve B or Frequency body015;
- authorize Donchian execution;
- deploy the Worker;
- authorize real capital.

Migration `006` is transactional, idempotent, and uses bounded lock and statement timeouts. It adds observability columns and indexes and performs conservative historical backfill. It never copies the ambiguous legacy `ticket` into order/deal/position identity fields.

## Required source state

```text
branch = agent/stage10c-observability-repair
minimum head = 5ad05ed
worktree = clean
```

Use the latest remote head because this runbook and validation files may add later commits without changing migration semantics.

## Files

```text
infra/supabase/validation/006_stage10c_observability_preflight.sql
infra/supabase/migrations/006_stage10c_observability.sql
infra/supabase/validation/006_stage10c_observability_validation.sql
```

## Execution method

Use the production Supabase project SQL Editor that already owns `public.signal_evals` and `public.trades`.

Do not paste service-role keys, database passwords, or connection strings into logs or chat.

### Optional macOS clipboard helper

From the repository root:

```bash
pbcopy < infra/supabase/validation/006_stage10c_observability_preflight.sql
pbcopy < infra/supabase/migrations/006_stage10c_observability.sql
pbcopy < infra/supabase/validation/006_stage10c_observability_validation.sql
```

Run one file at a time. Do not concatenate them.

## Checkpoint A1 — Preflight

Run:

```text
infra/supabase/validation/006_stage10c_observability_preflight.sql
```

Required result:

```text
required_tables.status = PASS
```

Record:

- `pre_migration_row_counts`;
- `stage10c_signal_inventory`;
- `stage10c_trade_inventory`;
- any rows returned by `duplicate_open_trade_identity_inventory`.

A non-empty duplicate-open-identity result is a review condition. Do not apply the migration until the rows are understood.

## Checkpoint A2 — Apply migration

Run the complete file:

```text
infra/supabase/migrations/006_stage10c_observability.sql
```

Expected SQL Editor result:

```text
Success. No rows returned.
```

The file contains its own `BEGIN` and `COMMIT`. Do not wrap it in another transaction and do not execute only selected statements.

If the migration fails:

1. preserve the full error text;
2. do not retry repeatedly;
3. do not deploy the Worker;
4. confirm that the transaction rolled back;
5. return to code review with the failing statement and database error.

## Checkpoint A3 — Post-migration validation

Run:

```text
infra/supabase/validation/006_stage10c_observability_validation.sql
```

Mandatory checks:

| Check | Required result |
|---|---|
| `required_columns` | `PASS`, violations `0` |
| `required_indexes` | `PASS`, violations `0` |
| `shadow_entry_not_error` | `PASS`, violations `0` |
| `v4430_trade_execution_mode` | `PASS`, violations `0` |
| `signal_eval_id_backfill` | `PASS`, violations `0` |
| `legacy_ticket_not_invented_as_order` | `PASS`, violations `0` |

Inventory-only results that must be recorded but do not automatically fail:

- `signal_eval_id_prefix_inventory`;
- `duplicate_signal_eval_id_inventory`;
- `trade_link_status_inventory`;
- `signal_decision_inventory`;
- `execution_mode_inventory`;
- `row_count_snapshot`.

## Row-count reconciliation

`signal_eval_rows` and `trade_rows` after migration must equal the preflight counts. Migration `006` updates existing rows but does not insert or delete signal/trade rows.

```text
post signal_eval_rows = pre signal_eval_rows
post trade_rows       = pre trade_rows
```

A mismatch is a blocker for Worker deployment.

## Checkpoint A pass criteria

```text
preflight required tables = PASS
no unexplained duplicate open trade identity
migration execution = SUCCESS
all mandatory validation checks = PASS
signal row count unchanged
trade row count unchanged
no Worker deployment performed
```

When these conditions pass, record the SQL outputs and proceed only after review to Checkpoint B.

## Checkpoint B — Reserved, do not execute yet

After explicit approval:

```text
1. Deploy Worker v3.3.0-stage10c-observability.
2. Verify /trading/health version.
3. Send controlled signal_eval shadow payload.
4. Send controlled trade_open and trade_close payloads using test-only identities.
5. Verify decision semantics, execution mode, reason separation, and single-row linking.
6. Confirm no existing Stage10C trade was modified by test data.
```

Detailed payload commands will be issued only after Checkpoint A passes.

## Rollback boundary

Migration `006` is additive. Immediate operational rollback before Worker deployment is simply:

```text
do not deploy Worker v3.3.0
```

Do not drop new columns or indexes as an ad-hoc rollback. Existing Worker versions ignore additive columns. If a data-backfill defect is found, correct it through a reviewed repair migration rather than destructive manual SQL.
