# F4 Forward Testing — Checklist de Configuración

## Estado: LISTO PARA DESPLEGAR

---

## Paso 1 — Supabase: Crear tabla `trades`

Ejecutar en Supabase SQL Editor (`fxttpblmiqgoerbvfons.supabase.co`):

```
infra/supabase/migrations/004_trades.sql
```

Tablas creadas:
- `trades` — eventos live del EA (open, close, init, circuit_break)
- Vista `live_performance` — KPIs por símbolo/versión

---

## Paso 2 — Copiar archivos al MT5

En Mac Wine, MT5 path típico: `~/Library/Containers/net.metaquotes.wine.metatrader5/Data/drive_c/Program Files/MetaTrader 5/`

```bash
# Copiar EA
cp mql5/experts/v2_ema_adx_pullback/EMA_ADX_Pullback_v23.mq5 \
   "<MT5_PATH>/MQL5/Experts/"

# Copiar includes (si no están ya)
cp mql5/include/Logger.mqh       "<MT5_PATH>/MQL5/Include/"
cp mql5/include/CircuitBreaker.mqh "<MT5_PATH>/MQL5/Include/"
```

---

## Paso 3 — Compilar en MetaEditor

1. Abrir MetaEditor (F4 desde MT5)
2. Abrir `Experts/EMA_ADX_Pullback_v23.mq5`
3. Compilar (F7)
4. Verificar: 0 errores, 0 warnings críticos

---

## Paso 4 — Configurar WebRequest

MT5 → Tools → Options → Expert Advisors → Allow WebRequest:

```
https://algo-trading-mt5.momentumcoaches-content.workers.dev
```

---

## Paso 5 — Adjuntar EA en gráfico

1. Abrir gráfico USDJPY H4 (demo account)
2. Arrastrar `EMA_ADX_Pullback_v23` al gráfico
3. Configurar inputs:
   - `InpWebhookSecret` = valor del `.env` → `CF_WORKER_SECRET`
   - `InpWebhookEnable` = true
   - `InpMagic` = 20260410
   - Resto: defaults (EMA=21, ADX=14, adxMin=25, atrSL=1.5, atrTP=2.5)
4. Activar "Allow live trading" ✓

---

## Paso 6 — Validar webhook

Verificar en Supabase que llegó el evento `init`:

```sql
SELECT * FROM trades ORDER BY created_at DESC LIMIT 5;
```

---

## Paso 7 — Monitoreo F4

**Referencia OOS**: USDJPY v2.3 → PF = 1.70, DD = 2.1%

**Criterio de drift (kill-switch manual)**:
- Alerta si PF live < 1.36 (80% de 1.70) después de ≥ 20 trades
- Pausar EA si DD live > 5% (circuit breaker automático ya activo)

**Consulta de seguimiento semanal**:
```sql
SELECT * FROM live_performance WHERE symbol = 'USDJPY';
```

---

## Archivos creados en esta fase

| Archivo | Descripción |
|---------|-------------|
| `mql5/experts/v2_ema_adx_pullback/EMA_ADX_Pullback_v23.mq5` | EA principal F4 |
| `mql5/include/Logger.mqh` | Logger con WebRequest real (v2.0) |
| `mql5/include/CircuitBreaker.mqh` | Kill-switch drawdown (sin cambios) |
| `infra/supabase/migrations/004_trades.sql` | Tabla trades + vista live_performance |
| `infra/worker/src/index.ts` | Cloudflare Worker (ya desplegado) |
