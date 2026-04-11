-- Migration: 005_fix_trades_event_type.sql
-- Descripción: Fix para tabla trades creada sin columna event_type
-- Causa: CREATE TABLE IF NOT EXISTS saltó tabla existente en 004_trades.sql
-- Ejecutar en: Supabase SQL Editor

-- Agregar columna event_type si no existe
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS event_type TEXT;

-- Rellenar filas existentes con valor por defecto (si las hay)
UPDATE trades SET event_type = 'open' WHERE event_type IS NULL;

-- Aplicar constraint NOT NULL ahora que todas las filas tienen valor
ALTER TABLE trades
    ALTER COLUMN event_type SET NOT NULL;

-- Crear índice si no existe
CREATE INDEX IF NOT EXISTS idx_trades_event_type ON trades(event_type);

-- Recrear la vista (necesita event_type)
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
