-- Permit explicit demo execution while preserving the existing Stage10 modes.
-- The raw payload already distinguishes capital authorization; this constraint
-- keeps the canonical execution_mode column equally truthful.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.signal_evals
    DROP CONSTRAINT IF EXISTS signal_evals_execution_mode_check;
ALTER TABLE public.signal_evals
    ADD CONSTRAINT signal_evals_execution_mode_check CHECK (
        execution_mode IS NULL OR execution_mode IN ('SHADOW_ONLY', 'REAL', 'DEMO')
    );

ALTER TABLE public.trades
    DROP CONSTRAINT IF EXISTS trades_execution_mode_check;
ALTER TABLE public.trades
    ADD CONSTRAINT trades_execution_mode_check CHECK (
        execution_mode IS NULL OR execution_mode IN ('SHADOW_ONLY', 'REAL', 'DEMO')
    );

COMMIT;
