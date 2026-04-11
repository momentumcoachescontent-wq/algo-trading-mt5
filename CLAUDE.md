# CLAUDE.md

# algo-trading-mt5 — Contexto para Claude Code

## Estado actual
- Fase: F3 iteración 13 — EA v2.3 en test
- Par primario: USDJPY H4
- EA activo: `mql5/experts/v1_ema_adx/A_v2_3.mq5`

## Reglas duras (NO negociables)
- Sin martingala, sin grid — hardcoded en código
- Sin comprar EAs externos
- Kill-switch DD: usar 25% en backtests (5% invalida resultados)
- Toda modificación de parámetros → backtest completo antes de producción
- #ifndef guards en MQL5, nunca #pragma once
- shift=1 en todos los datos OHLC (iLow/iHigh/iClose)

## Stack técnico
- MT5 vía Wine (Mac)
- MQL5 para EAs
- Python: vectorbt, DuckDB, Streamlit (research platform)
- Infra: Cloudflare Worker + Supabase
- Worker: `infra/worker/src/index.ts` → deploy via `wrangler`
- Worker URL: algo-trading-mt5.momentumcoaches-content.workers.dev

## Skills disponibles
- /mnt/skills/user/mql5-ea-structure/SKILL.md
- /mnt/skills/user/mql5-risk-calculator/SKILL.md
- /mnt/skills/user/mql5-http-logger/SKILL.md
- /mnt/skills/user/mql5-market-structure/SKILL.md
- /mnt/skills/user/mql5-multitimeframe/SKILL.md
- /mnt/skills/user/mql5-position-management/SKILL.md

## Contexto completo
Ver: docs/dev-log/, docs/decisions/ADR-*/, PHASE.md, CHANGELOG.md