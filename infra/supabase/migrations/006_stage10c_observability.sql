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
    strategy_variant = COALESCE(
        strategy_variant,
        raw_payload ->> 'strategy_variant',
        phase
    ),
    guard_version = COALESCE(guard_version, raw_payload ->> 'guard_version'),
    magic_number = COALESCE(
        magic_number,
        CASE
            WHEN COALESCE(raw_payload ->> 'magic_number', raw_payload ->> 'magic', '')
                 ~ '^\d+$'
            THEN COALESCE(
                raw_payload ->> 'magic_number',
                raw_payload ->> 'magic'
            )::BIGINT
            ELSE NULL
        END
    ),
    boot_id = COALESCE(boot_id, raw_payload ->> 'boot_id'),
    bar_h4 = COALESCE(
        bar_h4,
        CASE
            WHEN COALESCE(
                raw_payload ->> 'bar_h4',
                raw_payload ->> 'bar_time_h4',
                raw_payload ->> 'bar_time',
                ''
            ) ~ '^\d{4}-\d{2}-\d{2}'
            THEN COALESCE(
                raw_payload ->> 'bar_h4',
                raw_payload ->> 'bar_time_h4',
                raw_payload ->> 'bar_time'
            )::TIMESTAMPTZ
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

-- Stable legacy IDs allow exact historical joins without imposing a foreign
-- key over incomplete evidence. Future Worker rows use their own deterministic
-- v1 ID contract consistently across signal_eval and trade_open payloads.
UPDATE public.signal_evals
SET signal_eval_id = 'stage10c-sig-legacy-' || MD5(
    COALESCE(symbol, '') || '|' ||
    COALESCE(ea_version, '') || '|' ||
    COALESCE(strategy_variant, phase, '') || '|' ||
    COALESCE(eval_time::TEXT, bar_h4::TEXT, '') || '|' ||
    COALESCE(direction, '') || '|' ||
    COALESCE(entry_price::TEXT, '')
)
WHERE signal_eval_id IS NULL;

-- Recover only unique historical signal -> open-position matches. The join is
-- intentionally exact and does not manufacture an order ticket.
WITH candidate_links AS (
    SELECT
        t.id AS trade_id,
        MIN(s.signal_eval_id) AS signal_eval_id,
        COUNT(*) AS match_count
    FROM public.trades t
    JOIN public.signal_evals s
      ON s.symbol = t.symbol
     AND s.ea_version = t.ea_version
     AND LOWER(COALESCE(s.direction, '')) = LOWER(COALESCE(t.direction, ''))
     AND s.eval_time = t.open_time
     AND s.entry_price IS NOT NULL
     AND t.open_price IS NOT NULL
     AND ABS(s.entry_price - t.open_price) <= 0.00001
     AND (
          UPPER(COALESCE(s.action, '')) IN ('ENTRY_READY', 'ENTRY_ACCEPTED')
          OR COALESCE(s.would_have_traded, FALSE) = TRUE
          OR s.decision IN ('ENTRY_READY', 'ENTRY_READY_REAL_ALLOWED')
     )
    WHERE t.event_type = 'open'
      AND t.signal_eval_id IS NULL
    GROUP BY t.id
    HAVING COUNT(*) = 1
)
UPDATE public.trades t
SET signal_eval_id = c.signal_eval_id
FROM candidate_links c
WHERE t.id = c.trade_id;

-- The v4.43.0 payload proves that trade_open.ticket may equal position_id.
-- Therefore migration 006 never backfills order_ticket or deal_ticket from the
-- ambiguous legacy ticket column. Explicit IDs may be recovered only from
-- raw_payload fields when present.
UPDATE public.trades
SET order_ticket = (raw_payload ->> 'order_ticket')::BIGINT
WHERE order_ticket IS NULL
  AND raw_payload IS NOT NULL
  AND COALESCE(raw_payload ->> 'order_ticket', '') ~ '^\d+$';

UPDATE public.trades
SET deal_ticket = (raw_payload ->> 'deal_ticket')::BIGINT
WHERE deal_ticket IS NULL
  AND raw_payload IS NOT NULL
  AND COALESCE(raw_payload ->> 'deal_ticket', '') ~ '^\d+$';

-- Exact known Stage10C control backfill only. Other historical rows remain NULL
-- rather than receiving an inferred execution mode.
UPDATE public.trades
SET execution_mode = 'REAL'
WHERE execution_mode IS NULL
  AND symbol = 'USDJPY'
  AND ea_version = 'v4.43.0';

UPDATE public.trades
SET strategy_variant = COALESCE(strategy_variant, phase)
WHERE strategy_variant IS NULL;

UPDATE public.trades
SET link_status = CASE
    WHEN event_type = 'open'
         AND signal_eval_id IS NOT NULL
         AND position_id IS NOT NULL
         AND order_ticket IS NOT NULL
        THEN 'LEGACY_LINKED_SIGNAL_ORDER_POSITION'
    WHEN event_type = 'open'
         AND signal_eval_id IS NOT NULL
         AND position_id IS NOT NULL
        THEN 'LEGACY_LINKED_SIGNAL_POSITION_ORDER_UNKNOWN'
    WHEN event_type = 'open'
         AND position_id IS NOT NULL
         AND ticket = position_id
        THEN 'LEGACY_POSITION_TICKET_ORDER_UNKNOWN'
    WHEN event_type = 'open' AND position_id IS NOT NULL
        THEN 'LEGACY_POSITION_ONLY_NO_SIGNAL_LINK'
    WHEN event_type = 'open'
        THEN 'LEGACY_OPEN_IDENTITY_INCOMPLETE'
    WHEN event_type = 'close'
         AND position_id IS NOT NULL
         AND deal_ticket IS NOT NULL
        THEN 'LEGACY_CLOSE_POSITION_AND_DEAL'
    WHEN event_type = 'close' AND position_id IS NOT NULL
        THEN 'LEGACY_CLOSE_POSITION_DEAL_UNKNOWN'
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
COMMENT ON COLUMN public.trades.order_ticket IS
    'Explicit MT5 order ticket only; never inferred from legacy trade_open.ticket when position_id exists.';
COMMENT ON COLUMN public.trades.deal_ticket IS
    'Explicit MT5 deal ticket only; ambiguous legacy ticket values remain unclassified.';
COMMENT ON COLUMN public.trades.link_status IS
    'Explicit signal/order/position linking quality; never implies missing links.';

COMMIT;
