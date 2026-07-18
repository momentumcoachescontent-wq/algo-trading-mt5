-- Migration: 006_stage10c_observability.sql
-- Purpose: normalize Stage10C decision semantics and trade identity/linking.
-- Apply before deploying Worker v3.3.0-stage10c-observability.
-- This migration does not change strategy, risk, execution policy, or capital.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

-- signal_evals is the authoritative decision ledger.
ALTER TABLE public.signal_evals
    ADD COLUMN IF NOT EXISTS signal_eval_id TEXT,
    ADD COLUMN IF NOT EXISTS decision TEXT,
    ADD COLUMN IF NOT EXISTS technical_signal_status TEXT,
    ADD COLUMN IF NOT EXISTS execution_mode TEXT,
    ADD COLUMN IF NOT EXISTS order_send_allowed BOOLEAN,
    ADD COLUMN IF NOT EXISTS would_have_traded BOOLEAN,
    ADD COLUMN IF NOT EXISTS primary_signal_reason TEXT,
    ADD COLUMN IF NOT EXISTS governance_guard_reason TEXT,
    ADD COLUMN IF NOT EXISTS execution_denied_reason TEXT,
    ADD COLUMN IF NOT EXISTS policy_name TEXT,
    ADD COLUMN IF NOT EXISTS strategy_variant TEXT,
    ADD COLUMN IF NOT EXISTS guard_version TEXT,
    ADD COLUMN IF NOT EXISTS magic_number BIGINT,
    ADD COLUMN IF NOT EXISTS boot_id TEXT,
    ADD COLUMN IF NOT EXISTS bar_h4 TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS raw_payload JSONB;

-- Preserve legacy trade columns required by the current Worker, then add the
-- normalized identity and observability fields.
ALTER TABLE public.trades
    ADD COLUMN IF NOT EXISTS position_id BIGINT,
    ADD COLUMN IF NOT EXISTS open_time TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS close_time TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS close_reason TEXT,
    ADD COLUMN IF NOT EXISTS dd_pct NUMERIC(12,6),
    ADD COLUMN IF NOT EXISTS order_ticket BIGINT,
    ADD COLUMN IF NOT EXISTS deal_ticket BIGINT,
    ADD COLUMN IF NOT EXISTS signal_eval_id TEXT,
    ADD COLUMN IF NOT EXISTS execution_mode TEXT,
    ADD COLUMN IF NOT EXISTS strategy_variant TEXT,
    ADD COLUMN IF NOT EXISTS guard_version TEXT,
    ADD COLUMN IF NOT EXISTS magic_number BIGINT,
    ADD COLUMN IF NOT EXISTS boot_id TEXT,
    ADD COLUMN IF NOT EXISTS link_status TEXT,
    ADD COLUMN IF NOT EXISTS raw_payload JSONB;

-- Historical signal metadata can be recovered from raw_payload without
-- claiming links that were never emitted by the EA.
UPDATE public.signal_evals
SET
    execution_mode = COALESCE(
        execution_mode,
        raw_payload #>> '{execution_scope,mode}',
        raw_payload ->> 'execution_mode'
    ),
    order_send_allowed = COALESCE(
        order_send_allowed,
        CASE
            WHEN LOWER(COALESCE(
                raw_payload #>> '{execution_scope,order_send_allowed}',
                raw_payload ->> 'order_send_allowed',
                ''
            )) IN ('true', '1', 'yes', 'on') THEN TRUE
            WHEN LOWER(COALESCE(
                raw_payload #>> '{execution_scope,order_send_allowed}',
                raw_payload ->> 'order_send_allowed',
                ''
            )) IN ('false', '0', 'no', 'off') THEN FALSE
            ELSE NULL
        END
    ),
    would_have_traded = COALESCE(
        would_have_traded,
        CASE
            WHEN LOWER(COALESCE(raw_payload ->> 'would_have_traded', ''))
                 IN ('true', '1', 'yes', 'on') THEN TRUE
            WHEN LOWER(COALESCE(raw_payload ->> 'would_have_traded', ''))
                 IN ('false', '0', 'no', 'off') THEN FALSE
            ELSE NULL
        END
    ),
    policy_name = COALESCE(
        policy_name,
        raw_payload #>> '{execution_scope,policy_name}',
        raw_payload ->> 'policy_name'
    ),
    strategy_variant = COALESCE(strategy_variant, raw_payload ->> 'strategy_variant'),
    guard_version = COALESCE(guard_version, raw_payload ->> 'guard_version'),
    boot_id = COALESCE(boot_id, raw_payload ->> 'boot_id'),
    bar_h4 = COALESCE(
        bar_h4,
        CASE
            WHEN COALESCE(raw_payload ->> 'bar_h4', '')
                 ~ '^\d{4}-\d{2}-\d{2}'
            THEN (raw_payload ->> 'bar_h4')::TIMESTAMPTZ
            ELSE NULL
        END
    )
WHERE raw_payload IS NOT NULL;

UPDATE public.signal_evals
SET
    technical_signal_status = COALESCE(
        technical_signal_status,
        CASE
            WHEN UPPER(COALESCE(action, '')) IN ('ENTRY_READY', 'ENTRY_ACCEPTED')
                THEN 'ENTRY_READY'
            WHEN block_reason IS NOT NULL THEN 'BLOCKED'
            WHEN COALESCE(h4_signal, 0) <> 0 THEN 'RAW_SIGNAL'
            ELSE 'NO_SIGNAL'
        END
    ),
    primary_signal_reason = COALESCE(
        primary_signal_reason,
        CASE
            WHEN LOWER(COALESCE(block_reason, '')) SIMILAR TO
                 '%(position_open|session_not_allowed|friday_no_new_entry|circuit_break|daily_dd|weekly_pause|governance|symbol_not_allowed|max_positions|spread_guard)%'
                THEN NULL
            ELSE block_reason
        END
    ),
    governance_guard_reason = COALESCE(
        governance_guard_reason,
        CASE
            WHEN LOWER(COALESCE(block_reason, '')) SIMILAR TO
                 '%(position_open|session_not_allowed|friday_no_new_entry|circuit_break|daily_dd|weekly_pause|governance|symbol_not_allowed|max_positions|spread_guard)%'
                THEN block_reason
            ELSE NULL
        END
    ),
    execution_denied_reason = COALESCE(
        execution_denied_reason,
        raw_payload #>> '{execution_scope,reason}',
        raw_payload ->> 'execution_denied_reason',
        raw_payload ->> 'scope_reason'
    );

-- Correct historical semantic labels conservatively. Entry evidence always
-- outranks a legacy decision='ERROR' summary label.
UPDATE public.signal_evals
SET decision = CASE
    WHEN UPPER(COALESCE(action, '')) IN ('ENTRY_READY', 'ENTRY_ACCEPTED')
         OR COALESCE(would_have_traded, FALSE) = TRUE
    THEN CASE
        WHEN UPPER(COALESCE(execution_mode, '')) = 'SHADOW_ONLY'
             OR order_send_allowed = FALSE
            THEN 'ENTRY_READY_SHADOW_ONLY_BLOCKED'
        WHEN order_send_allowed = TRUE
            THEN 'ENTRY_READY_REAL_ALLOWED'
        ELSE 'ENTRY_READY'
    END
    WHEN block_reason IS NOT NULL
    THEN CASE
        WHEN LOWER(block_reason) SIMILAR TO
             '%(position_open|session_not_allowed|friday_no_new_entry|circuit_break|daily_dd|weekly_pause|governance|symbol_not_allowed|max_positions|spread_guard)%'
            THEN 'BLOCKED_BY_GOVERNANCE_GUARD'
        ELSE 'BLOCKED_BY_TECHNICAL_GUARD'
    END
    ELSE COALESCE(NULLIF(decision, ''), 'NO_SIGNAL')
END
WHERE decision IS NULL
   OR decision = ''
   OR (
       UPPER(decision) = 'ERROR'
       AND (
           UPPER(COALESCE(action, '')) IN ('ENTRY_READY', 'ENTRY_ACCEPTED')
           OR COALESCE(would_have_traded, FALSE) = TRUE
       )
   );

-- Stable legacy correlation IDs allow future trade payloads to point to old
-- signal rows without asserting a database foreign key over incomplete data.
UPDATE public.signal_evals
SET signal_eval_id = 'stage10c-sig-legacy-' || MD5(
    COALESCE(symbol, '') || '|' ||
    COALESCE(ea_version, '') || '|' ||
    COALESCE(strategy_variant, '') || '|' ||
    COALESCE(bar_h4::TEXT, eval_time::TEXT, '') || '|' ||
    COALESCE(direction, '') || '|' ||
    COALESCE(entry_price::TEXT, '')
)
WHERE signal_eval_id IS NULL;

-- Event-specific ticket backfill. Do not copy ticket into position_id.
UPDATE public.trades
SET order_ticket = ticket
WHERE order_ticket IS NULL AND event_type = 'open';

UPDATE public.trades
SET deal_ticket = ticket
WHERE deal_ticket IS NULL AND event_type = 'close';

-- Exact known Stage10C control backfill only. Other historical rows remain NULL
-- rather than receiving an inferred execution mode.
UPDATE public.trades
SET execution_mode = 'REAL'
WHERE execution_mode IS NULL
  AND symbol = 'USDJPY'
  AND ea_version = 'v4.43.0';

UPDATE public.trades
SET link_status = CASE
    WHEN event_type = 'open' AND position_id IS NOT NULL
        THEN 'LEGACY_POSITION_ONLY_NO_SIGNAL_LINK'
    WHEN event_type = 'open'
        THEN 'LEGACY_OPEN_IDENTITY_INCOMPLETE'
    WHEN event_type = 'close' AND position_id IS NOT NULL
        THEN 'LEGACY_CLOSE_POSITION_ONLY'
    ELSE 'LEGACY_UNLINKED'
END
WHERE link_status IS NULL;

CREATE INDEX IF NOT EXISTS idx_signal_evals_signal_eval_id
    ON public.signal_evals(signal_eval_id);
CREATE INDEX IF NOT EXISTS idx_signal_evals_execution_mode
    ON public.signal_evals(execution_mode);
CREATE INDEX IF NOT EXISTS idx_signal_evals_decision
    ON public.signal_evals(decision);
CREATE INDEX IF NOT EXISTS idx_signal_evals_strategy_variant
    ON public.signal_evals(strategy_variant);

CREATE INDEX IF NOT EXISTS idx_trades_signal_eval_id
    ON public.trades(signal_eval_id);
CREATE INDEX IF NOT EXISTS idx_trades_order_ticket
    ON public.trades(order_ticket);
CREATE INDEX IF NOT EXISTS idx_trades_deal_ticket
    ON public.trades(deal_ticket);
CREATE INDEX IF NOT EXISTS idx_trades_open_link_identity
    ON public.trades(position_id, symbol, execution_mode, strategy_variant)
    WHERE close_time IS NULL;

COMMENT ON COLUMN public.signal_evals.decision IS
    'Normalized semantic decision; valid shadow entries are not ERROR.';
COMMENT ON COLUMN public.trades.link_status IS
    'Explicit signal/order/position linking quality; never implies missing links.';

COMMIT;
