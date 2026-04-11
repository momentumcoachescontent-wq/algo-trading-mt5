-- Migration: 003_research_runs.sql
-- Proyecto: fxttpblmiqgoerbvfons.supabase.co
-- Descripción: Tablas para Research Platform (F3+)
-- Ejecutar en: Supabase SQL Editor

-- ── research_runs ────────────────────────────────────────────────────────
-- Cada row es un run completo de WFA o backtest single
CREATE TABLE IF NOT EXISTS research_runs (
    run_id       TEXT PRIMARY KEY,
    ea_version   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL DEFAULT 'H4',
    params       JSONB NOT NULL DEFAULT '{}',
    metrics      JSONB NOT NULL DEFAULT '{}',
    run_type     TEXT NOT NULL DEFAULT 'wfa',  -- 'wfa' | 'single' | 'mc'
    passed_f3    BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para queries frecuentes
CREATE INDEX IF NOT EXISTS idx_research_runs_ea_version ON research_runs(ea_version);
CREATE INDEX IF NOT EXISTS idx_research_runs_symbol     ON research_runs(symbol);
CREATE INDEX IF NOT EXISTS idx_research_runs_passed_f3  ON research_runs(passed_f3);
CREATE INDEX IF NOT EXISTS idx_research_runs_created_at ON research_runs(created_at DESC);

-- ── wfa_windows ──────────────────────────────────────────────────────────
-- Detalle de cada ventana IS/OOS de un run WFA
CREATE TABLE IF NOT EXISTS wfa_windows (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
    window_idx   INTEGER NOT NULL,
    is_from      TIMESTAMPTZ,
    is_to        TIMESTAMPTZ,
    oos_from     TIMESTAMPTZ,
    oos_to       TIMESTAMPTZ,
    is_metrics   JSONB DEFAULT '{}',
    oos_metrics  JSONB DEFAULT '{}',
    UNIQUE(run_id, window_idx)
);

CREATE INDEX IF NOT EXISTS idx_wfa_windows_run_id ON wfa_windows(run_id);

-- ── mc_results ────────────────────────────────────────────────────────────
-- Resultados agregados de Monte Carlo (sin los arrays completos — demasiado grandes)
CREATE TABLE IF NOT EXISTS mc_results (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES research_runs(run_id),
    n_simulations   INTEGER NOT NULL,
    base_pf         NUMERIC(8,4),
    base_dd         NUMERIC(8,4),
    pf_p5           NUMERIC(8,4),
    pf_p25          NUMERIC(8,4),
    pf_p50          NUMERIC(8,4),
    pf_p75          NUMERIC(8,4),
    pf_p95          NUMERIC(8,4),
    prob_pf_gt_1    NUMERIC(5,2),
    prob_pf_gt_1_2  NUMERIC(5,2),
    dd_p50          NUMERIC(8,4),
    dd_p95          NUMERIC(8,4),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── sleeve_kpis ───────────────────────────────────────────────────────────
-- KPIs por sleeve para comparación y portfolio allocation
CREATE TABLE IF NOT EXISTS sleeve_kpis (
    sleeve_id        TEXT PRIMARY KEY,
    ea_version       TEXT,
    symbol           TEXT,
    timeframe        TEXT,
    n_trades         INTEGER,
    profit_factor    NUMERIC(8,4),
    win_rate         NUMERIC(5,4),
    wl_ratio         NUMERIC(8,4),
    sharpe           NUMERIC(8,4),
    sortino          NUMERIC(8,4),
    calmar           NUMERIC(8,4),
    ulcer_index      NUMERIC(8,4),
    max_dd_pct       NUMERIC(8,4),
    robustness_index NUMERIC(8,4),
    is_pf            NUMERIC(8,4),
    oos_pf           NUMERIC(8,4),
    composite_score  NUMERIC(6,4),
    saved_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ── RLS policies (habilitar si multi-usuario) ─────────────────────────────
-- Por ahora: acceso directo via service_role key (solo desde pipeline local)
-- En F5 hardening: activar RLS y policies por usuario

-- ALTER TABLE research_runs ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "service_role_only" ON research_runs
--     USING (auth.role() = 'service_role');

-- ── Vista útil: mejores runs por símbolo ─────────────────────────────────
CREATE OR REPLACE VIEW best_runs_by_symbol AS
SELECT
    symbol,
    ea_version,
    run_id,
    (metrics->>'avg_oos_pf')::numeric AS oos_pf,
    (metrics->>'avg_robustness_index')::numeric AS ri,
    (metrics->>'max_oos_dd')::numeric AS max_dd,
    passed_f3,
    created_at
FROM research_runs
WHERE run_type = 'wfa'
ORDER BY symbol, oos_pf DESC;
