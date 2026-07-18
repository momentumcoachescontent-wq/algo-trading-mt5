-- Preflight: 006_stage10c_observability_preflight.sql
-- Purpose: capture a read-only baseline before applying migration 006.

BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '30s';

SELECT
    'preflight_context' AS check_name,
    CURRENT_DATABASE() AS database_name,
    CURRENT_USER AS database_user,
    NOW() AT TIME ZONE 'UTC' AS checked_at_utc;

SELECT
    'required_tables' AS check_name,
    TO_REGCLASS('public.signal_evals') AS signal_evals_table,
    TO_REGCLASS('public.trades') AS trades_table,
    CASE
        WHEN TO_REGCLASS('public.signal_evals') IS NOT NULL
         AND TO_REGCLASS('public.trades') IS NOT NULL
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status;

SELECT
    'pre_migration_row_counts' AS check_name,
    (SELECT COUNT(*) FROM public.signal_evals) AS signal_eval_rows,
    (SELECT COUNT(*) FROM public.trades) AS trade_rows,
    (SELECT COUNT(*) FROM public.trades WHERE close_time IS NULL) AS open_trade_rows;

SELECT
    'stage10c_signal_inventory' AS check_name,
    ea_version,
    COALESCE(decision, '<NULL>') AS decision,
    COUNT(*) AS row_count
FROM public.signal_evals
WHERE ea_version IN ('v4.43.0', 'v4.43.1')
GROUP BY ea_version, COALESCE(decision, '<NULL>')
ORDER BY ea_version, decision;

SELECT
    'stage10c_trade_inventory' AS check_name,
    ea_version,
    symbol,
    COALESCE(event_type, '<NULL>') AS event_type,
    COUNT(*) AS row_count
FROM public.trades
WHERE ea_version IN ('v4.43.0', 'v4.43.1')
GROUP BY ea_version, symbol, COALESCE(event_type, '<NULL>')
ORDER BY ea_version, symbol, event_type;

-- Multiple open rows with the same known identity require review before deployment.
SELECT
    'duplicate_open_trade_identity_inventory' AS check_name,
    position_id,
    symbol,
    COUNT(*) AS open_rows
FROM public.trades
WHERE close_time IS NULL
  AND position_id IS NOT NULL
GROUP BY position_id, symbol
HAVING COUNT(*) > 1
ORDER BY open_rows DESC, symbol, position_id;

ROLLBACK;
