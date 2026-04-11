# Research Platform — Architecture Document
## `algo-trading-research` v1.0

---

## Problema que resuelve

El workflow anterior dependía de capturas de pantalla del MT5 Strategy Tester:
- Sin acceso programático a los datos de trades
- Sin reproducibilidad entre runs
- Sin Monte Carlo real
- Sin análisis multi-activo simultáneo
- Sin logging histórico de experimentos

Esta plataforma reemplaza MT5 como motor de investigación. **MT5 pasa a ser exclusivamente capa de ejecución live.**

---

## Principios de Diseño

1. **Separación total**: Research ≠ Execution. Nunca mezclar.
2. **Reproducibilidad**: Todo run tiene un `run_id` con hash de parámetros.
3. **Velocidad**: vectorbt corre WFA en segundos, no en horas.
4. **Trazabilidad**: Cada resultado se persiste en Supabase con metadatos completos.
5. **Observable**: Dashboard Streamlit local, sin dependencia de infraestructura externa.

---

## Stack de Tecnología

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESEARCH PLATFORM                            │
├─────────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                     │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ MT5 Python API   │───▶│ DuckDB (local)   │                  │
│  │ (extracción)     │    │ OHLCV + ticks    │                  │
│  └──────────────────┘    └──────────────────┘                  │
│                                                                 │
│  RESEARCH ENGINE                                                │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ vectorbt         │    │ statsmodels      │                  │
│  │ WFA vectorizado  │    │ ADF / HMM regime │                  │
│  │ Monte Carlo      │    │ detection        │                  │
│  └──────────────────┘    └──────────────────┘                  │
│                                                                 │
│  PORTFOLIO LAYER                                                │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ PyPortfolioOpt   │    │ Sleeve Scorer    │                  │
│  │ HRP allocation   │    │ Sharpe/Sortino   │                  │
│  │ CVaR             │    │ Ulcer / RI       │                  │
│  └──────────────────┘    └──────────────────┘                  │
│                                                                 │
│  PERSISTENCE                                                    │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ Supabase         │    │ Cloudflare Worker│                  │
│  │ run results      │    │ webhook ingest   │                  │
│  │ param history    │    │ (existente)      │                  │
│  └──────────────────┘    └──────────────────┘                  │
│                                                                 │
│  VISUALIZATION                                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │ Streamlit Dashboard (local :8501)        │                  │
│  │ Equity curves / WFA windows / MC         │                  │
│  │ Sleeve comparison / Portfolio alloc      │                  │
│  └──────────────────────────────────────────┘                  │
├─────────────────────────────────────────────────────────────────┤
│  EXECUTION (separado, solo F4+)                                 │
│  MT5 → EAs MQL5 → Cloudflare Worker → Supabase                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Estructura del Repositorio

```
algo-trading-mt5/
├── python/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── extract_mt5.py          # Extracción MT5 Python API
│   │   ├── store.py                # DuckDB CRUD
│   │   └── schema.sql              # DDL tablas locales
│   ├── research/
│   │   ├── __init__.py
│   │   ├── signals.py              # Lógica de señales (espejo del EA)
│   │   ├── wfa_engine.py           # Walk-Forward Analysis vectorizado
│   │   ├── monte_carlo.py          # Simulación Monte Carlo
│   │   └── regime.py               # Detección de régimen de mercado
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── sleeve_scorer.py        # KPIs por sleeve (Sharpe, Sortino, RI, Ulcer)
│   │   └── sleeve_allocator.py     # HRP multi-sleeve con PyPortfolioOpt
│   ├── pipeline/
│   │   ├── __init__.py
│   │   └── run_backtest.py         # CLI orquestador
│   └── infra/
│       └── supabase_client.py      # Persistencia de resultados
├── dashboard/
│   ├── app.py                      # Streamlit entry point
│   └── pages/
│       ├── 01_wfa_results.py
│       ├── 02_monte_carlo.py
│       ├── 03_sleeve_comparison.py
│       └── 04_portfolio_allocation.py
├── configs/
│   ├── v1_9.yaml                   # Config EA v1.9 validado
│   └── v2_3.yaml                   # Config EA v2.3 en test
├── infra/
│   └── supabase/
│       └── migrations/
│           └── 003_research_runs.sql
├── tests/
│   ├── test_signals.py
│   ├── test_wfa_engine.py
│   └── test_sleeve_scorer.py
├── docs/
│   ├── ARCHITECTURE.md             # Este documento
│   ├── RESEARCH_WORKFLOW.md        # Workflow paso a paso
│   └── ADR-010-research-platform.md
├── requirements-research.txt
└── .env.example
```

---

## Flujo de Trabajo Completo

```
1. EXTRACCIÓN
   python -m python.pipeline.run_backtest extract \
     --symbol USDJPY --timeframe H4 --from 2020-01-01

2. BACKTEST + WFA
   python -m python.pipeline.run_backtest wfa \
     --config configs/v2_3.yaml --symbol USDJPY

3. MONTE CARLO
   python -m python.pipeline.run_backtest monte-carlo \
     --run-id <run_id> --n 1000

4. PORTFOLIO (multi-sleeve)
   python -m python.pipeline.run_backtest portfolio \
     --sleeves v1_9,v2_3 --symbols USDJPY,EURUSD

5. DASHBOARD
   streamlit run dashboard/app.py
```

---

## Criterios de Aceptación por Fase

| Fase | Criterio |
|------|----------|
| F3 (actual) | PF IS > 1.20, OOS > 1.10, RI ≥ 0.90, DD < 10%, trades IS ≥ 80 |
| F4 Forward | Resultados live en Supabase, drift < 20% vs OOS |
| F5 Hardening | Circuit breaker activo, alertas Cloudflare Worker |
| F7 Optimization | Regime routing reduce DD 15%+ vs baseline |
| F8 Portfolio | HRP allocation, correlación inter-sleeve < 0.4 |
