-- Migration: 004_trades.sql
-- Descripción: Tabla de trades live para F4 Forward Testing
-- Ejecutar en: Supabase SQL Editor

-- ── trades ────────────────────────────────────────────────────────────────
-- Cada row es un evento de trade enviado por el EA vía Cloudflare Worker
-- Estructura alineada con el payload del Worker (index.ts)
CREATE TABLE IF NOT EXISTS trades (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Identificación del trade
    ticket       BIGINT,                      -- MT5 ticket (open) o deal (close)
    symbol       TEXT NOT NULL,               -- ej: USDJPY
    direction    TEXT NOT NULL,               -- 'BUY' | 'SELL'
    event_type   TEXT NOT NULL,               -- 'open' | 'close' | 'init' | 'circuit_break'

    -- Precios y sizing
    open_price   NUMERIC(12,5),
    close_price  NUMERIC(12,5),               -- NULL en eventos 'open'
    lots         NUMERIC(8,4),
    sl           NUMERIC(12,5),
    tp           NUMERIC(12,5),
    pnl          NUMERIC(12,2),               -- NULL en eventos 'open'

    -- Metadatos del EA
    ea_version   TEXT,                        -- ej: 'v2.3'
    phase        TEXT DEFAULT 'F4',           -- 'F4' | 'F5' | etc.

    -- Timestamps
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para queries frecuentes del dashboard
CREATE INDEX IF NOT EXISTS idx_trades_symbol      ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_ea_version  ON trades(ea_version);
CREATE INDEX IF NOT EXISTS idx_trades_event_type  ON trades(event_type);
CREATE INDEX IF NOT EXISTS idx_trades_created_at  ON trades(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_ticket      ON trades(ticket);

-- ── Vista: resumen de trades cerrados por símbolo ────────────────────────
CREATE OR REPLACE VIEW live_performance AS
SELECT
    symbol,
    ea_version,
    COUNT(*) FILTER (WHERE event_type = 'close')                         AS total_trades,
    COUNT(*) FILTER (WHERE event_type = 'close' AND pnl > 0)            AS wins,
    COUNT(*) FILTER (WHERE event_type = 'close' AND pnl <= 0)           AS losses,
    ROUND(
        COUNT(*) FILTER (WHERE event_type = 'close' AND pnl > 0)::numeric
        / NULLIF(COUNT(*) FILTER (WHERE event_type = 'close'), 0), 3
    )                                                                    AS win_rate,
    ROUND(SUM(pnl) FILTER (WHERE event_type = 'close'), 2)              AS total_pnl,
    ROUND(AVG(pnl) FILTER (WHERE event_type = 'close' AND pnl > 0), 2) AS avg_win,
    ROUND(AVG(ABS(pnl)) FILTER (WHERE event_type = 'close' AND pnl < 0), 2) AS avg_loss,
    ROUND(
        SUM(pnl) FILTER (WHERE event_type = 'close' AND pnl > 0)
        / NULLIF(ABS(SUM(pnl) FILTER (WHERE event_type = 'close' AND pnl < 0)), 0), 3
    )                                                                    AS profit_factor,
    MIN(created_at) FILTER (WHERE event_type = 'close')                 AS first_trade,
    MAX(created_at) FILTER (WHERE event_type = 'close')                 AS last_trade
FROM trades
GROUP BY symbol, ea_version;
