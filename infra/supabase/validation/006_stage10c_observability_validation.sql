-- Validation: 006_stage10c_observability_validation.sql
-- Purpose: read-only post-migration validation for Stage10C observability.
-- Run after 006_stage10c_observability.sql and before Worker v3.3.0 deploy.

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

-- 1. Required schema columns. Expected: missing_columns = 0.
WITH required_columns(table_name, column_name) AS (
    VALUES
        ('signal_evals', 'signal_eval_id'),
        ('signal_evals', 'decision'),
        ('signal_evals', 'technical_signal_status'),
        ('signal_evals', 'execution_mode'),
        ('signal_evals', 'order_send_allowed'),
        ('signal_evals', 'would_have_traded'),
        ('signal_evals', 'primary_signal_reason'),
        ('signal_evals', 'governance_guard_reason'),
        ('signal_evals', 'execution_denied_reason'),
        ('signal_evals', 'policy_name'),
        ('signal_evals', 'strategy_variant'),
        ('signal_evals', 'guard_version'),
        ('signal_evals', 'magic_number'),
        ('signal_evals', 'boot_id'),
        ('signal_evals', 'bar_h4'),
        ('signal_evals', 'raw_payload'),
        ('trades', 'order_ticket'),
        ('trades', 'deal_ticket'),
        ('trades', 'position_id'),
        ('trades', 'signal_eval_id'),
        ('trades', 'execution_mode'),
        ('trades', 'strategy_variant'),
        ('trades', 'guard_version'),
        ('trades', 'magic_number'),
        ('trades', 'boot_id'),
        ('trades', 'link_status'),
        ('trades', 'raw_payload')
), observed AS (
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN ('signal_evals', 'trades')
)
SELECT
    'required_columns' AS check_name,
    COUNT(*) FILTER (WHERE o.column_name IS NULL) AS violation_count,
    CASE WHEN COUNT(*) FILTER (WHERE o.column_name IS NULL) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    COALESCE(
        STRING_AGG(r.table_name || '.' || r.column_name, ', ' ORDER BY r.table_name, r.column_name)
            FILTER (WHERE o.column_name IS NULL),
        'none'
    ) AS detail
FROM required_columns r
LEFT JOIN observed o USING (table_name, column_name);

-- 2. Required indexes. Expected: violation_count = 0.
WITH required_indexes(index_name) AS (
    VALUES
        ('idx_signal_evals_signal_eval_id'),
        ('idx_signal_evals_execution_mode'),
        ('idx_signal_evals_decision'),
        ('idx_signal_evals_strategy_variant'),
        ('idx_trades_signal_eval_id'),
        ('idx_trades_order_ticket'),
        ('idx_trades_deal_ticket'),
        ('idx_trades_open_link_identity')
), observed AS (
    SELECT indexname AS index_name
    FROM pg_indexes
    WHERE schemaname = 'public'
)
SELECT
    'required_indexes' AS check_name,
    COUNT(*) FILTER (WHERE o.index_name IS NULL) AS violation_count,
    CASE WHEN COUNT(*) FILTER (WHERE o.index_name IS NULL) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    COALESCE(
        STRING_AGG(r.index_name, ', ' ORDER BY r.index_name)
            FILTER (WHERE o.index_name IS NULL),
        'none'
    ) AS detail
FROM required_indexes r
LEFT JOIN observed o USING (index_name);

-- 3. The decision constraint must preserve legacy values and allow every
-- normalized value emitted by the Stage10C observability contract.
WITH decision_constraint AS (
    SELECT PG_GET_CONSTRAINTDEF(c.oid, TRUE) AS definition
    FROM pg_constraint c
    JOIN pg_class rel ON rel.oid = c.conrelid
    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
    WHERE nsp.nspname = 'public'
      AND rel.relname = 'signal_evals'
      AND c.conname = 'signal_evals_decision_check'
      AND c.contype = 'c'
), evaluated AS (
    SELECT
        definition,
        POSITION('SIGNAL' IN definition) > 0
        AND POSITION('BLOCKED' IN definition) > 0
        AND POSITION('OPENED' IN definition) > 0
        AND POSITION('CLOSED' IN definition) > 0
        AND POSITION('ERROR' IN definition) > 0
        AND POSITION('ENTRY_READY_REAL_ALLOWED' IN definition) > 0
        AND POSITION('ENTRY_READY_SHADOW_ONLY_BLOCKED' IN definition) > 0
        AND POSITION('BLOCKED_BY_EXECUTION_SCOPE' IN definition) > 0
        AND POSITION('BLOCKED_BY_GOVERNANCE_GUARD' IN definition) > 0
        AND POSITION('BLOCKED_BY_TECHNICAL_GUARD' IN definition) > 0
        AND POSITION('RAW_SIGNAL' IN definition) > 0
        AND POSITION('NO_SIGNAL' IN definition) > 0 AS contract_ok
    FROM decision_constraint
)
SELECT
    'decision_constraint_contract' AS check_name,
    CASE WHEN COUNT(*) = 1 AND BOOL_AND(contract_ok) THEN 0 ELSE 1 END AS violation_count,
    CASE WHEN COUNT(*) = 1 AND BOOL_AND(contract_ok) THEN 'PASS' ELSE 'FAIL' END AS status,
    COALESCE(MAX(definition), 'constraint missing') AS detail
FROM evaluated;

-- 4. A valid shadow entry must never remain ERROR after backfill.
SELECT
    'shadow_entry_not_error' AS check_name,
    COUNT(*) AS violation_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'ENTRY_READY/ENTRY_ACCEPTED/would_have_traded shadow rows with decision=ERROR' AS detail
FROM public.signal_evals
WHERE UPPER(COALESCE(decision, '')) = 'ERROR'
  AND (
      UPPER(COALESCE(action, '')) LIKE 'ENTRY_READY%'
      OR UPPER(COALESCE(action, '')) = 'ENTRY_ACCEPTED'
      OR COALESCE(would_have_traded, FALSE) = TRUE
  )
  AND (
      UPPER(COALESCE(execution_mode, '')) = 'SHADOW_ONLY'
      OR order_send_allowed = FALSE
  );

-- 5. Known Stage10C control trade rows should have REAL execution mode.
SELECT
    'v4430_trade_execution_mode' AS check_name,
    COUNT(*) AS violation_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'USDJPY v4.43.0 trade rows with execution_mode missing or not REAL' AS detail
FROM public.trades
WHERE symbol = 'USDJPY'
  AND ea_version = 'v4.43.0'
  AND UPPER(COALESCE(execution_mode, '')) <> 'REAL';

-- 6. Canonical IDs should be present on all historical signal rows after backfill.
SELECT
    'signal_eval_id_backfill' AS check_name,
    COUNT(*) AS violation_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'signal_evals rows with null/blank canonical ID' AS detail
FROM public.signal_evals
WHERE NULLIF(BTRIM(signal_eval_id), '') IS NULL;

-- 7. Canonical IDs must use the governed prefix unless explicitly supplied by the EA.
-- Existing explicit non-governed IDs are reported for review, not automatically failed.
SELECT
    'signal_eval_id_prefix_inventory' AS check_name,
    COUNT(*) FILTER (
        WHERE signal_eval_id LIKE 'stage10c-sig-v1|%'
    ) AS canonical_count,
    COUNT(*) FILTER (
        WHERE signal_eval_id IS NOT NULL
          AND signal_eval_id NOT LIKE 'stage10c-sig-v1|%'
    ) AS explicit_or_legacy_count,
    COUNT(*) AS total_count
FROM public.signal_evals;

-- 8. Duplicate IDs are inventory only because retries/legacy duplicate events may exist.
SELECT
    'duplicate_signal_eval_id_inventory' AS check_name,
    COUNT(*) AS duplicate_id_groups,
    COALESCE(SUM(row_count - 1), 0) AS duplicate_rows_beyond_first
FROM (
    SELECT signal_eval_id, COUNT(*) AS row_count
    FROM public.signal_evals
    WHERE signal_eval_id IS NOT NULL
    GROUP BY signal_eval_id
    HAVING COUNT(*) > 1
) duplicates;

-- 9. Legacy ambiguous ticket must not be silently manufactured as order_ticket.
SELECT
    'legacy_ticket_not_invented_as_order' AS check_name,
    COUNT(*) AS violation_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'order_ticket equals ambiguous legacy position ticket without explicit raw order_ticket' AS detail
FROM public.trades
WHERE order_ticket IS NOT NULL
  AND position_id IS NOT NULL
  AND ticket = position_id
  AND order_ticket = ticket
  AND NULLIF(COALESCE(raw_payload ->> 'order_ticket', ''), '') IS NULL;

-- 10. Link-quality inventory. Review counts; no expected single distribution.
SELECT
    'trade_link_status_inventory' AS check_name,
    COALESCE(link_status, '<NULL>') AS link_status,
    COUNT(*) AS row_count
FROM public.trades
GROUP BY COALESCE(link_status, '<NULL>')
ORDER BY row_count DESC, link_status;

-- 11. Decision inventory after normalization.
SELECT
    'signal_decision_inventory' AS check_name,
    COALESCE(decision, '<NULL>') AS decision,
    COUNT(*) AS row_count
FROM public.signal_evals
GROUP BY COALESCE(decision, '<NULL>')
ORDER BY row_count DESC, decision;

-- 12. Execution-mode inventory by version.
SELECT
    'execution_mode_inventory' AS check_name,
    ea_version,
    COALESCE(execution_mode, '<NULL>') AS execution_mode,
    COUNT(*) AS row_count
FROM public.signal_evals
WHERE ea_version IN ('v4.43.0', 'v4.43.1')
GROUP BY ea_version, COALESCE(execution_mode, '<NULL>')
ORDER BY ea_version, execution_mode;

-- 13. Migration does not change strategy/risk fields; provide row-count snapshot.
SELECT
    'row_count_snapshot' AS check_name,
    (SELECT COUNT(*) FROM public.signal_evals) AS signal_eval_rows,
    (SELECT COUNT(*) FROM public.trades) AS trade_rows,
    (SELECT COUNT(*) FROM public.trades WHERE close_time IS NULL) AS open_trade_rows;

ROLLBACK;
