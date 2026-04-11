# Research Workflow — Procedimiento Operativo Estándar

## Prerequisitos

```bash
# 1. MT5 abierto en Mac (Wine)
# 2. Entorno Python activo
pip install -r requirements-research.txt

# 3. Variables de entorno configuradas
cp .env.example .env
# Editar .env con credenciales de Supabase
```

---

## Ciclo Estándar de Investigación

### PASO 1 — Extracción de Datos

```bash
# Extraer USDJPY H4 desde 2020 (para WFA completo)
python -m python.pipeline.run_backtest extract \
  --symbol USDJPY \
  --timeframe H4 \
  --from 2020-01-01

# Verificar que los datos quedaron en DuckDB
python -m python.pipeline.run_backtest verify --symbol USDJPY
```

**Output esperado:**
```
✓ USDJPY H4: 3,847 velas (2020-01-01 → 2026-04-10)
✓ Guardado en: data/market_data.duckdb
```

**Cuándo re-extraer:**
- Al iniciar un nuevo activo
- Semanalmente para mantener datos actualizados
- Nunca re-extraer solo para un run específico (DuckDB es incremental)

---

### PASO 2 — Configurar Parámetros del EA

Crear o editar un archivo YAML en `configs/`:

```yaml
# configs/v2_3.yaml
ea_version: "v2.3"
symbol: USDJPY
timeframe: H4

# Parámetros de señal
ema_period: 21
adx_period: 14
adx_min: 25.0
atr_period: 14
atr_sl_mult: 1.5
atr_tp_mult: 2.5        # Único cambio vs v2.2 (era 2.0)
body_threshold: 0.40

# Walk-Forward
wfa:
  is_months: 36          # 3 años In-Sample
  oos_months: 6          # 6 meses Out-of-Sample
  step_months: 6         # Avance de ventana

# Criterios de aceptación F3
acceptance:
  pf_is_min: 1.20
  pf_oos_min: 1.10
  robustness_index_min: 0.90
  max_dd_pct: 10.0
  min_trades_is: 80
```

---

### PASO 3 — Walk-Forward Analysis

```bash
python -m python.pipeline.run_backtest wfa \
  --config configs/v2_3.yaml \
  --symbol USDJPY \
  --save-to-supabase
```

**Output esperado:**
```
=== WFA Run: v2.3 / USDJPY H4 ===
Run ID: a3f7b2c1...

Ventana 1: IS 2020-01→2022-12  OOS 2023-01→2023-06
  IS:  PF=1.31  Trades=94  WR=34.0%  DD=7.2%
  OOS: PF=1.18  Trades=22  WR=36.4%  DD=5.1%

Ventana 2: IS 2020-07→2023-06  OOS 2023-07→2023-12
  IS:  PF=1.28  Trades=98  WR=33.7%  DD=8.1%
  OOS: PF=1.14  Trades=19  WR=31.6%  DD=6.3%

...

=== RESUMEN AGREGADO ===
PF IS promedio:   1.29
PF OOS promedio:  1.16
Robustness Index: 0.90
Max DD:           8.4%
Total trades IS:  412

✓ CRITERIOS F3 CUMPLIDOS
✓ Guardado en Supabase: run_id=a3f7b2c1
```

---

### PASO 4 — Monte Carlo

```bash
python -m python.pipeline.run_backtest monte-carlo \
  --run-id a3f7b2c1 \
  --n 1000
```

**Output esperado:**
```
=== Monte Carlo: 1000 permutaciones ===
Base OOS PF: 1.16

Distribución PF (OOS permutado):
  P5:   0.89   ← riesgo de ruina
  P25:  1.04
  P50:  1.16   ← mediana ≈ base (coherente)
  P75:  1.28
  P95:  1.47

Probabilidad PF > 1.0:  87.3%
Probabilidad PF > 1.2:  51.1%

Max DD P95: 14.2%

✓ Sistema robusto: P50 ≈ base OOS
⚠ P5 DD excede 10% — considerar position sizing conservador
```

---

### PASO 5 — Sleeve Comparison (multi-versión)

```bash
python -m python.pipeline.run_backtest compare-sleeves \
  --sleeves v1_9,v2_3 \
  --symbol USDJPY
```

---

### PASO 6 — Dashboard

```bash
streamlit run dashboard/app.py
# Abre http://localhost:8501
```

Páginas disponibles:
- **WFA Results**: Equity curve por ventana, tabla de métricas
- **Monte Carlo**: Distribución de PF y DD, percentiles
- **Sleeve Comparison**: Tabla comparativa, scatter Sharpe vs DD
- **Portfolio Allocation**: HRP weights (disponible F8)

---

## Reglas de Gobernanza

### Qué se persiste en Supabase
- Todo run con `--save-to-supabase` (por defecto activado)
- Formato: `run_id`, `ea_version`, `symbol`, `params_hash`, `metrics_json`, `timestamp`
- **Nunca borrar runs históricos** — son el historial de decisiones

### Qué NO se hace durante F3
- No correr WFA con datos post-OOS como nuevos IS (data leakage)
- No modificar `body_threshold` — ADR documenta que 0.40 es óptimo
- No testear trailing stop — ADR documenta que destruye avg_win

### Cuándo avanzar a F4
Solo cuando WFA cumpla **todos** los criterios de aceptación:
- PF IS > 1.20
- PF OOS > 1.10
- Robustness Index ≥ 0.90
- DD < 10%
- Trades IS ≥ 80
