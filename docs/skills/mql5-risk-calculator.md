---
name: mql5-risk-calculator
description: Calculate correct lot sizes by risk percentage in MQL5. Use this skill whenever computing position sizing, stop loss distances, or lot calculations in any MQL5 EA. Covers the exact formula for forex pairs, pip value calculation, and NormalizeDouble requirements. Always use this skill before writing any order-sending code.
---

# MQL5 Risk Calculator

## Fórmula completa de sizing por riesgo

```mql5
double CalculateLots(double slPoints) {
   double balance    = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount = balance * InpRisk / 100.0;

   double tickValue  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double point      = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   // Valor monetario por punto por lote
   double valuePerPoint = tickValue * point / tickSize;

   if(valuePerPoint <= 0 || slPoints <= 0) return 0;

   double lots = riskAmount / (slPoints * valuePerPoint);

   // Normalizar dentro de los límites del broker
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));

   return NormalizeDouble(lots, 2);
}
```

## Calcular SL y TP en puntos desde ATR

```mql5
void CalculateSLTP(double atr, ENUM_ORDER_TYPE orderType,
                   double &sl, double &tp) {
   double slDist = atr * InpAtrSL;
   double tpDist = atr * InpAtrTP;
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(orderType == ORDER_TYPE_BUY) {
      sl = NormalizeDouble(bid - slDist, _Digits);
      tp = NormalizeDouble(ask + tpDist, _Digits);
   } else {
      sl = NormalizeDouble(ask + slDist, _Digits);
      tp = NormalizeDouble(bid - tpDist, _Digits);
   }
}
```

## Enviar orden completa con sizing

```mql5
void OpenTrade(ENUM_ORDER_TYPE orderType, double atr) {
   double sl, tp;
   CalculateSLTP(atr, orderType, sl, tp);

   double entryPrice = (orderType == ORDER_TYPE_BUY)
      ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
      : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double slPoints = MathAbs(entryPrice - sl) / _Point;
   double lots     = CalculateLots(slPoints);

   if(lots <= 0) {
      Print("ERROR sizing: lots=0, balance insuficiente o SL=0");
      return;
   }

   bool result = (orderType == ORDER_TYPE_BUY)
      ? trade.Buy(lots, _Symbol, entryPrice, sl, tp, "EA_v1")
      : trade.Sell(lots, _Symbol, entryPrice, sl, tp, "EA_v1");

   if(!result)
      Print("ERROR orden: ", trade.ResultRetcodeDescription());
}
```

## Verificación del retcode

```mql5
// Después de trade.Buy() o trade.Sell()
if(trade.ResultRetcode() == TRADE_RETCODE_DONE) {
   Print("Orden OK ticket=", trade.ResultOrder());
} else {
   Print("Orden FAIL: ", trade.ResultRetcode(),
         " - ", trade.ResultRetcodeDescription());
}
```

## Reglas críticas
- SIEMPRE `NormalizeDouble(price, _Digits)` en SL y TP
- SIEMPRE verificar `lots > 0` antes de enviar
- NUNCA hardcodear lotaje — siempre calculado por riesgo
- En Strategy Tester usar ACCOUNT_BALANCE, no ACCOUNT_EQUITY
