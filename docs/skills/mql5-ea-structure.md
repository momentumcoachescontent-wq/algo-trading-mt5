---
name: mql5-ea-structure
description: Build correct Expert Advisor (EA) structure in MQL5 for MetaTrader 5. Use this skill whenever writing, reviewing, or debugging any MQL5 EA file (.mq5). Covers OnInit/OnTick/OnDeinit lifecycle, IsNewBar pattern, CTrade class usage, Magic Number isolation, input parameters, and Strategy Tester compatibility. Always use this skill before writing any EA code.
---

# MQL5 EA Structure

## Required skeleton — every EA starts here

```mql5
#include <Trade\Trade.mqh>

// ── Input parameters (visible in Strategy Tester) ──────────
input int    InpMagic     = 20260331;
input double InpRisk      = 1.0;      // % risk per trade
input int    InpEmaFast   = 21;
input int    InpEmaSlow   = 50;
input int    InpAdxPeriod = 14;
input double InpAdxMin    = 25.0;
input int    InpAtrPeriod = 14;
input double InpAtrSL     = 1.5;
input double InpAtrTP     = 3.0;

// ── Global objects ──────────────────────────────────────────
CTrade trade;
int    handleEmaFast, handleEmaSlow, handleAdx, handleAtr;
datetime lastBarTime = 0;

// ── OnInit ──────────────────────────────────────────────────
int OnInit() {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(10);

   handleEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   handleEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   handleAdx     = iADX(_Symbol, PERIOD_CURRENT, InpAdxPeriod);
   handleAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);

   if(handleEmaFast == INVALID_HANDLE || handleEmaSlow == INVALID_HANDLE ||
      handleAdx == INVALID_HANDLE     || handleAtr == INVALID_HANDLE) {
      Print("ERROR: No se pudo crear indicador");
      return INIT_FAILED;
   }
   return INIT_SUCCEEDED;
}

// ── OnDeinit ────────────────────────────────────────────────
void OnDeinit(const int reason) {
   IndicatorRelease(handleEmaFast);
   IndicatorRelease(handleEmaSlow);
   IndicatorRelease(handleAdx);
   IndicatorRelease(handleAtr);
}

// ── OnTick ──────────────────────────────────────────────────
void OnTick() {
   if(!IsNewBar()) return;   // Solo actuar en nueva vela
   // lógica de señal va aquí
}
```

## IsNewBar — patrón correcto

```mql5
bool IsNewBar() {
   datetime currentBar = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(currentBar != lastBarTime) {
      lastBarTime = currentBar;
      return true;
   }
   return false;
}
```

## Leer valores de indicadores (buffer)

```mql5
double GetIndicatorValue(int handle, int bufferIndex, int shift) {
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, bufferIndex, 0, shift + 1, buf) < shift + 1)
      return EMPTY_VALUE;
   return buf[shift];
}

// Uso:
double emaFast0 = GetIndicatorValue(handleEmaFast, 0, 0); // vela actual
double emaFast1 = GetIndicatorValue(handleEmaFast, 0, 1); // vela anterior
double emaSlow0 = GetIndicatorValue(handleEmaSlow, 0, 0);
double emaSlow1 = GetIndicatorValue(handleEmaSlow, 0, 1);
double adx      = GetIndicatorValue(handleAdx, 0, 1);     // ADX principal
double atr      = GetIndicatorValue(handleAtr, 0, 1);
```

## Detectar cruce EMA

```mql5
bool IsBullishCross() {
   return (emaFast1 < emaSlow1) && (emaFast0 > emaSlow0) && (adx > InpAdxMin);
}
bool IsBearishCross() {
   return (emaFast1 > emaSlow1) && (emaFast0 < emaSlow0) && (adx > InpAdxMin);
}
```

## Verificar posición abierta con Magic Number

```mql5
bool HasOpenPosition() {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(PositionGetSymbol(i) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
   }
   return false;
}
```

## Reglas críticas
- SIEMPRE verificar `HasOpenPosition()` antes de abrir
- NUNCA usar `Sleep()` en OnTick
- SIEMPRE leer buffer con shift=1 (vela cerrada), no shift=0
- SIEMPRE `IndicatorRelease()` en OnDeinit
- Magic Number debe ser único por EA/cuenta
