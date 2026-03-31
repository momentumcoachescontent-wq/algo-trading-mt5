# STRATEGY-v1.md
# Especificación EA v1 — EMA Cross + ADX + ATR
# Fecha: 2026-03-31 | Fase: F1 | Estado: APROBADO

## Resumen en una línea
Trend-following en EURUSD H1 usando cruce de EMAs confirmado
por ADX, con sizing por riesgo fijo y SL/TP derivados de ATR.

## Parámetros fijos (no tocar hasta completar F3)

| Parámetro        | Valor       | Razón                                  |
|------------------|-------------|----------------------------------------|
| Activo           | EURUSD      | Alta liquidez, spread bajo, datos 10y+ |
| Timeframe        | H1          | Suficientes señales, menos ruido       |
| EMA rápida       | 21 períodos | Balance señal/ruido en H1              |
| EMA lenta        | 50 períodos | Confirma tendencia media               |
| ADX período      | 14 períodos | Estándar de la industria               |
| ADX umbral       | > 25        | Filtra mercados en rango               |
| ATR período      | 14 períodos | Volatilidad reciente normalizada       |
| SL multiplicador | 1.5 × ATR   | Espacio para respirar sin sobreexposer |
| TP multiplicador | 3.0 × ATR   | R:R = 2:1, expectancy positiva         |
| Riesgo por trade | 1% capital  | Máximo absoluto en v1                  |
| Magic Number     | 20260331    | Fecha de creación — único por EA       |

## Reglas de entrada

### Long (compra)
1. EMA 21 cruza ARRIBA de EMA 50 (en vela cerrada)
2. ADX(14) > 25 en el momento del cruce
3. No hay posición abierta con este Magic Number
4. Entrada: apertura de la siguiente vela

### Short (venta)
1. EMA 21 cruza ABAJO de EMA 50 (en vela cerrada)
2. ADX(14) > 25 en el momento del cruce
3. No hay posición abierta con este Magic Number
4. Entrada: apertura de la siguiente vela

## Reglas de salida
- SL fijo: precio_entrada ± (ATR(14) × 1.5)
- TP fijo: precio_entrada ± (ATR(14) × 3.0)
- Sin trailing stop en v1
- Sin cierre manual — el sistema cierra solo

## Restricciones operativas
- Una sola posición abierta a la vez
- Entrada solo en nueva vela (OnTimer o IsNewBar)
- Sin filtro de horario en v1
- Sin filtro de noticias en v1
- Sin martingale, sin grid, sin recuperación

## Métricas de aceptación para pasar a F4

| Métrica              | Mínimo requerido         |
|----------------------|--------------------------|
| Profit Factor        | > 1.2                    |
| Max Drawdown         | < 20% del capital        |
| Expectancy           | > 0 por trade            |
| Total trades         | > 100 (estadística válida)|
| Meses ganadores      | > 55% de los meses       |
| Out-of-sample        | PF > 1.1 en período OOS  |

## Kill-switch
Si el drawdown alcanza 5% del capital en cualquier
momento, el EA se detiene y no abre nuevas posiciones
hasta reinicio manual con revisión de logs.

## Lo que NO es esta estrategia
- No es martingale
- No promedia perdedores
- No usa indicadores adicionales en v1
- No predice — reacciona a lo que ya ocurrió
- No es "el sistema definitivo" — es la línea base

## Versiones futuras (no ahora)
- v1.1: filtro horario (evitar apertura/cierre NY)
- v1.2: filtro spread dinámico
- v2.0: trailing stop basado en ATR
- v3.0: multi-activo (GBPUSD, USDJPY)
