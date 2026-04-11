# ADR-010: Research Platform — Reemplazar MT5 Strategy Tester como motor de investigación

**Fecha:** 2026-04-10
**Estado:** Aceptado
**Autor:** Neto / Sistema

---

## Contexto

El workflow de investigación en F3 dependía del MT5 Strategy Tester como única fuente de verdad. Los resultados se capturaban como imágenes, sin acceso programático a datos granulares de trades, sin capacidad de Monte Carlo robusto, sin análisis de portafolio multi-activo y sin histórico reproducible de experimentos.

Los problemas concretos identificados:

1. **Opacidad**: Los resultados son imágenes. No hay datos exportables automáticamente.
2. **Lentitud**: Un sweep de parámetros requiere N runs manuales en la UI de MT5.
3. **Falta de reproducibilidad**: No existe un `run_id` que vincule parámetros con resultados.
4. **Sin Monte Carlo real**: MT5 no ofrece permutación de trades para distribución de outcomes.
5. **Sin análisis de portafolio**: No hay forma de evaluar correlación entre sleeves desde MT5.
6. **Sin persistencia histórica**: Los resultados no se acumulan en una base de datos consultable.

---

## Decisión

Construir una plataforma de research local en Python que utilice MT5 **únicamente** como fuente de datos históricos (via MT5 Python API) y como capa de ejecución live (F4+). Toda la investigación se realiza fuera de MT5.

### Stack seleccionado

| Componente | Herramienta | Razón |
|---|---|---|
| Extracción de datos | `MetaTrader5` (pip) | API oficial, acceso directo a OHLCV limpio |
| Almacenamiento local | `DuckDB` + Parquet | SQL sobre archivos, sin servidor, 10× más rápido que pandas |
| Motor de backtest/WFA | `vectorbt` | WFA vectorizado, Monte Carlo nativo, 1000× más rápido que Strategy Tester |
| Detección de régimen | `statsmodels` (HMM) | Prepara F7 — regime routing |
| Scoring de sleeves | Custom (`sleeve_scorer.py`) | Sharpe, Sortino, Ulcer Index, Robustness Index |
| Asignación de portafolio | `PyPortfolioOpt` (HRP) | Prepara F8 — multi-sleeve allocation |
| Persistencia de resultados | `Supabase` (existente) | Proyecto ya activo, runs acumulables con metadata |
| Ingestión webhook | Cloudflare Worker (existente) | Worker ya deployado en `algo-trading-mt5.momentumcoaches-content.workers.dev` |
| Dashboard | `Streamlit` | Python puro, Plotly charts, local :8501 |

---

## Alternativas Consideradas

### A — Seguir con MT5 Strategy Tester + mejor exportación manual
- **Pros**: Sin nueva infraestructura.
- **Contras**: Irreproducible, sin Monte Carlo real, sin portafolio, escala O(n) manual.
- **Descartado**: No resuelve el problema raíz.

### B — Backtrader
- **Pros**: Maduro, bien documentado.
- **Contras**: Sin vectorización nativa, Monte Carlo requiere código custom, lento para WFA multi-ventana.
- **Descartado**: vectorbt es superior en velocidad y features para este caso.

### C — Zipline (Quantopian fork)
- **Contras**: Legado, mantenimiento bajo, orientado a equity US.
- **Descartado**: Mencionado en ecosistema Python como descartado.

### D — FreqAI / FinRL
- **Contras**: Orientados a crypto y RL respectivamente. Overhead de ML no justificado en F3.
- **Reservado**: FreqAI evaluable en F7 (regime routing con ML).

---

## Consecuencias

### Positivas
- WFA corre en segundos vs horas en MT5.
- Monte Carlo con n=1000 permutaciones disponible por defecto.
- Cada run tiene `run_id` = hash SHA256 de parámetros + símbolo + ventana.
- Resultados acumulados en Supabase: consultables, comparables históricamente.
- Regime detection lista para F7 sin reescribir la plataforma.
- HRP allocation lista para F8 sin reescribir la plataforma.

### Negativas / Trade-offs
- Requiere que MT5 esté abierto en la misma máquina para extracción (Wine en Mac).
- La señal Python debe ser un espejo exacto del EA MQL5 — riesgo de divergencia.
- `vectorbt` tiene una curva de aprendizaje moderada para WFA personalizado.

### Mitigaciones
- `signals.py` es la fuente de verdad de la lógica. El EA MQL5 se sincroniza con ella.
- Tests unitarios en `tests/test_signals.py` validan paridad señal Python ↔ MQL5.
- MT5 Python API permite extracción sin UI — se puede automatizar via script.

---

## Referencias
- ADR-001 a ADR-009: decisiones previas del sistema
- `ARCHITECTURE.md`: diagrama de capas completo
- `RESEARCH_WORKFLOW.md`: procedimiento paso a paso
- Fases F3→F8: `PHASE.md` en repo principal
