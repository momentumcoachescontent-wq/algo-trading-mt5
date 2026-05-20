//+------------------------------------------------------------------+
//|  EMA_MTF_v4321_touch_zone_score.mq5                             |
//|  Expert Advisor v4321 — TouchZoneEngine 3-tier scoring          |
//|  Símbolo primario: USDJPY  |  Timeframe: H4                    |
//|  Versión: 4321.0  |  Fecha: 2026-05-20                         |
//+------------------------------------------------------------------+
//
//  CAMBIOS vs v2.3 (EMA_ADX_Pullback_v23):
//    - TouchZoneEngine sustituye al binary touch gate (0.50 ATR)
//    - Score continuo 0-1 por tier: exact / soft / extended
//    - Gate de entrada viva: exact + soft (score ≥ 0.5 ↔ dist ≤ 0.50 ATR)
//      → misma cobertura que v2.3, sin cambio en número de señales
//    - Opportunity Ledger: candidatos extended registrados en RAM
//    - signal_eval enviado en cada evaluación de touch zone
//    - entry_cohort etiqueta cada trade: EXACT/SOFT × LONG/SHORT
//    - ML Veto en shadow mode: logea score, nunca bloquea
//    - Riesgo idéntico a v2.3: 1%, SL=1.5×ATR, TP=2.5×ATR
//    - Sin trailing stop
//
//  LOGS ESTRUCTURADOS:
//    [TOUCH_ZONE_SCORE]    — en cada nueva barra con touch ≠ none
//    [OPPORTUNITY_LEDGER]  — candidatos extended (no entran vivos)
//    [ENTRY_COHORT]        — al confirmar una entrada
//    [DECISION_BLOCKED]    — cuándo y por qué no se entra
//    [ENTRY_ACCEPTED]      — justo antes de ejecutar la orden
//    [ML_VETO_SHADOW]      — score ML (shadow, no bloquea)
//
//  DEPENDENCIAS:
//    • Include/CircuitBreaker.mqh  — kill-switch 5% drawdown
//    • Include/Logger.mqh          — webhook + SignalEvalTZ/TradeOpenTZ
//    • Include/TouchZoneEngine.mqh — motor 3-tier
//    • <Trade\Trade.mqh>           — CTrade librería estándar
//
//  PRIMERA EJECUCIÓN:
//    1. Copiar *.mq5 → MQL5/Experts/
//    2. Copiar Include/*.mqh → MQL5/Include/
//    3. Compilar (F7)
//    4. MT5 → Options → Expert Advisors → WebRequest →
//       añadir: https://algo-trading-mt5.momentumcoaches-content.workers.dev
//    5. Adjuntar en gráfico USDJPY H4 con "Allow live trading" ✓
//+------------------------------------------------------------------+

#include <Trade\Trade.mqh>
#include <CircuitBreaker.mqh>
#include <Logger.mqh>
#include <TouchZoneEngine.mqh>


//+------------------------------------------------------------------+
//|  Parámetros de entrada                                            |
//+------------------------------------------------------------------+

input group   "=== IDENTIFICACIÓN ==="
input int     InpMagic         = 20260520;    // Magic Number único
input string  InpEAVersion     = "v4321";     // Versión para logging

input group   "=== WEBHOOK ==="
input string  InpWebhookSecret = "";          // Secret X-EA-Secret
input bool    InpWebhookEnable = true;        // Activar envío al Worker

input group   "=== INDICADORES ==="
input int     InpEmaPeriod     = 21;          // EMA período
input int     InpAdxPeriod     = 14;          // ADX período
input double  InpAdxMin        = 25.0;        // ADX mínimo
input int     InpAtrPeriod     = 14;          // ATR período

input group   "=== TOUCH ZONE ENGINE ==="
input double  InpTZExactMax    = 0.25;        // Tier EXACT: 0 – N×ATR
input double  InpTZSoftMax     = 0.50;        // Tier SOFT gate (live entry)
input double  InpTZExtendedMax = 1.50;        // Tier EXTENDED: N×ATR (ledger)

input group   "=== SEÑAL ==="
input double  InpBodyThresh    = 0.40;        // Body ratio mínimo
input int     InpLookback      = 50;          // Ventana HH/HL estructura

input group   "=== GESTIÓN DE RIESGO ==="
input double  InpRisk          = 1.0;         // Riesgo por trade (% balance)
input double  InpAtrSL         = 1.5;         // SL = N × ATR
input double  InpAtrTP         = 2.5;         // TP = N × ATR
input double  InpKillDD        = 5.0;         // Circuit breaker DD%


//+------------------------------------------------------------------+
//|  Objetos globales                                                 |
//+------------------------------------------------------------------+

CTrade            trade;
CCircuitBreaker   cb;
CLogger           logger;
CTouchZoneEngine  tzEngine;

int      hEma, hAdx, hAtr;
datetime lastBarTime = 0;


//+------------------------------------------------------------------+
//|  Helpers — lectura de buffers (shift=1 en todos)                 |
//+------------------------------------------------------------------+

double GetEMA(int shift)   { double b[1]; CopyBuffer(hEma, 0, shift, 1, b); return b[0]; }
double GetATR(int shift)   { double b[1]; CopyBuffer(hAtr, 0, shift, 1, b); return b[0]; }
double GetADX(int shift)   { double b[1]; CopyBuffer(hAdx, 0, shift, 1, b); return b[0]; }
double GetPDI(int shift)   { double b[1]; CopyBuffer(hAdx, 1, shift, 1, b); return b[0]; }
double GetNDI(int shift)   { double b[1]; CopyBuffer(hAdx, 2, shift, 1, b); return b[0]; }

double GetClose(int shift) { double b[1]; CopyClose(_Symbol, PERIOD_CURRENT, shift, 1, b); return b[0]; }
double GetOpen(int shift)  { double b[1]; CopyOpen (_Symbol, PERIOD_CURRENT, shift, 1, b); return b[0]; }
double GetHigh(int shift)  { double b[1]; CopyHigh (_Symbol, PERIOD_CURRENT, shift, 1, b); return b[0]; }
double GetLow(int shift)   { double b[1]; CopyLow  (_Symbol, PERIOD_CURRENT, shift, 1, b); return b[0]; }


//+------------------------------------------------------------------+
//|  Estructura de mercado HH/HL (alcista)                           |
//+------------------------------------------------------------------+

bool IsHHHL(int refShift = 1)
{
   int    barsNeeded = InpLookback * 2 + refShift;
   double highs[], lows[];
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows,  true);
   if(CopyHigh(_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, highs) <= 0) return false;
   if(CopyLow (_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, lows)  <= 0) return false;

   double currHigh = -DBL_MAX, currLow = DBL_MAX;
   double prevHigh = -DBL_MAX, prevLow = DBL_MAX;

   for(int i = refShift; i < refShift + InpLookback; i++)
   {
      if(highs[i] > currHigh) currHigh = highs[i];
      if(lows[i]  < currLow)  currLow  = lows[i];
   }
   for(int i = refShift + InpLookback; i < refShift + InpLookback * 2; i++)
   {
      if(highs[i] > prevHigh) prevHigh = highs[i];
      if(lows[i]  < prevLow)  prevLow  = lows[i];
   }
   return (currHigh > prevHigh) && (currLow > prevLow);
}


//+------------------------------------------------------------------+
//|  Estructura de mercado LL/LH (bajista)                           |
//+------------------------------------------------------------------+

bool IsLLLH(int refShift = 1)
{
   int    barsNeeded = InpLookback * 2 + refShift;
   double highs[], lows[];
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows,  true);
   if(CopyHigh(_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, highs) <= 0) return false;
   if(CopyLow (_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, lows)  <= 0) return false;

   double currHigh = -DBL_MAX, currLow = DBL_MAX;
   double prevHigh = -DBL_MAX, prevLow = DBL_MAX;

   for(int i = refShift; i < refShift + InpLookback; i++)
   {
      if(highs[i] > currHigh) currHigh = highs[i];
      if(lows[i]  < currLow)  currLow  = lows[i];
   }
   for(int i = refShift + InpLookback; i < refShift + InpLookback * 2; i++)
   {
      if(highs[i] > prevHigh) prevHigh = highs[i];
      if(lows[i]  < prevLow)  prevLow  = lows[i];
   }
   return (currHigh < prevHigh) && (currLow < prevLow);
}


//+------------------------------------------------------------------+
//|  Body ratio de barra[shift]                                       |
//+------------------------------------------------------------------+

double BodyRatio(int shift)
{
   double o = GetOpen(shift), c = GetClose(shift);
   double h = GetHigh(shift), l = GetLow(shift);
   double range = h - l;
   if(range <= 0.0) return 0.0;
   return MathAbs(c - o) / range;
}


//+------------------------------------------------------------------+
//|  Cálculo de lote (1% riesgo sobre SL)                            |
//+------------------------------------------------------------------+

double CalcLots(double slPoints)
{
   if(slPoints <= 0.0) return 0.01;

   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmt   = balance * (InpRisk / 100.0);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double lotStep   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(tickValue <= 0.0 || tickSize <= 0.0) return minLot;

   double valuePerPoint = tickValue / tickSize;
   double lots = riskAmt / (slPoints / _Point * valuePerPoint);

   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(lots, minLot);
   lots = MathMin(lots, maxLot);
   return lots;
}


//+------------------------------------------------------------------+
//|  Posición abierta con este Magic                                  |
//+------------------------------------------------------------------+

bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionSelectByTicket(PositionGetTicket(i)))
         if(PositionGetInteger(POSITION_MAGIC) == InpMagic &&
            PositionGetString(POSITION_SYMBOL) == _Symbol)
            return true;
   }
   return false;
}


//+------------------------------------------------------------------+
//|  ML Veto — shadow mode (solo logea, nunca bloquea)               |
//+------------------------------------------------------------------+
//  Computa un heurístico provisional para registro. La inferencia
//  real del modelo se activará cuando ML Veto salga de shadow.

double MLVetoShadowScore(double touchScore, double adx, double bodyRatio)
{
   // Heurístico: combinación lineal simple normalizada
   // Rango esperado: 0.0 (vetaría) – 1.0 (aprobaría)
   double raw = (touchScore * 0.5) + (MathMin(adx, 50.0) / 50.0 * 0.3)
              + (bodyRatio * 0.2);
   return MathMin(MathMax(raw, 0.0), 1.0);
}


//+------------------------------------------------------------------+
//|  OnInit                                                           |
//+------------------------------------------------------------------+

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(10);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   hEma = iMA (_Symbol, PERIOD_CURRENT, InpEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   hAdx = iADX(_Symbol, PERIOD_CURRENT, InpAdxPeriod);
   hAtr = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);

   if(hEma == INVALID_HANDLE || hAdx == INVALID_HANDLE || hAtr == INVALID_HANDLE)
   {
      Print("ERROR: No se pudo crear indicadores");
      return INIT_FAILED;
   }

   tzEngine.Init(InpTZExactMax, InpTZSoftMax, InpTZExtendedMax);
   cb.Init(InpKillDD);
   logger.Init(InpWebhookSecret, InpMagic, InpEAVersion, InpWebhookEnable);
   logger.EAInit(cb.GetInitialBalance());

   PrintFormat("EA v4321 iniciado | %s %s | Magic=%d | Risk=%.1f%% | TZ=%.2f/%.2f/%.2f",
               _Symbol, EnumToString(PERIOD_CURRENT), InpMagic, InpRisk,
               InpTZExactMax, InpTZSoftMax, InpTZExtendedMax);
   return INIT_SUCCEEDED;
}


//+------------------------------------------------------------------+
//|  OnDeinit                                                         |
//+------------------------------------------------------------------+

void OnDeinit(const int reason)
{
   logger.EADeinit(reason);
   IndicatorRelease(hEma);
   IndicatorRelease(hAdx);
   IndicatorRelease(hAtr);
}


//+------------------------------------------------------------------+
//|  OnTrade — captura cierres de posición                            |
//+------------------------------------------------------------------+

void OnTrade()
{
   HistorySelect(TimeCurrent() - 60, TimeCurrent());
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0) continue;
      if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetInteger(dealTicket, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;

      string dir    = (HistoryDealGetInteger(dealTicket, DEAL_TYPE) == DEAL_TYPE_BUY) ? "BUY" : "SELL";
      double price  = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
      double volume = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
      double pnl    = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
      logger.TradeClose(dealTicket, dir, price, volume, pnl, cb.CurrentDrawdown());
      break;
   }
}


//+------------------------------------------------------------------+
//|  OnTick — lógica principal (una vez por vela nueva H4)           |
//+------------------------------------------------------------------+

void OnTick()
{
   // ── 1. Circuit breaker ──────────────────────────────────────────
   if(!cb.IsOperational())
   {
      logger.CircuitBreak(cb.CurrentDrawdown());
      ExpertRemove();
      return;
   }

   // ── 2. Nueva vela H4 ────────────────────────────────────────────
   datetime barTime[1];
   if(CopyTime(_Symbol, PERIOD_CURRENT, 0, 1, barTime) <= 0) return;
   if(barTime[0] == lastBarTime) return;
   lastBarTime = barTime[0];

   // ── 3. Solo un trade a la vez ───────────────────────────────────
   if(HasOpenPosition()) return;

   // ── 4. Leer indicadores en barra[1] (ya cerrada) ────────────────
   double ema    = GetEMA(1);
   double atr    = GetATR(1);
   double adx    = GetADX(1);
   double pdi    = GetPDI(1);
   double ndi    = GetNDI(1);
   double close1 = GetClose(1);
   double open1  = GetOpen(1);

   if(atr <= 0.0) return;

   // ── 5. TouchZoneEngine: evaluar distancia precio–EMA ────────────
   double         dist   = MathAbs(close1 - ema) / atr;
   TouchZoneResult tz    = tzEngine.Evaluate(dist);

   // Ignorar barras sin contacto (ningún tier útil)
   if(tz.tier == TOUCH_NONE) return;

   // ── 6. Determinar dirección candidata ───────────────────────────
   int    candidateDir  = (close1 > ema) ? 1 : -1;   // 1=LONG, -1=SHORT
   string candidateDirS = (candidateDir == 1) ? "BUY" : "SELL";
   int    h4Signal      = candidateDir;

   // Log estructurado de score
   PrintFormat("[TOUCH_ZONE_SCORE] symbol=%s tier=%s score=%.3f dist_atr=%.3f atr=%.5f version=%s",
               _Symbol, tz.mode, tz.score, dist, atr, tz.rule_version);

   // ── 7. Extended touch → Opportunity Ledger, no entra vivo ───────
   if(!tz.is_live_entry)
   {
      tzEngine.LedgerAdd(barTime[0], _Symbol, candidateDir, tz.score, atr, dist);

      PrintFormat("[OPPORTUNITY_LEDGER] symbol=%s dir=%s score=%.3f dist_atr=%.3f ledger_count=%d/%d",
                  _Symbol, candidateDirS, tz.score, dist,
                  tzEngine.LedgerCount(), TZ_LEDGER_SIZE);
      PrintFormat("[DECISION_BLOCKED] reason=extended_touch symbol=%s score=%.3f tier=%s",
                  _Symbol, tz.score, tz.mode);

      logger.SignalEvalTZ(
         _Symbol, candidateDirS, h4Signal,
         tz.mode, tz.score, atr, dist,
         "", tz.rule_version,
         "extended_touch", cb.IsOperational(), cb.CurrentDrawdown()
      );
      return;
   }

   // ── 8. Filtros de señal (exact + soft tier) ──────────────────────

   // 8a. ADX mínimo
   if(adx < InpAdxMin)
   {
      PrintFormat("[DECISION_BLOCKED] reason=adx_filter symbol=%s adx=%.1f min=%.1f score=%.3f",
                  _Symbol, adx, InpAdxMin, tz.score);
      return;
   }

   // 8b. Body ratio
   double bodyR = BodyRatio(1);

   // 8c. Evaluar señal LONG
   bool longOK = IsHHHL(1)          &&   // estructura alcista
                 (close1 > ema)     &&   // sobre EMA
                 (pdi > ndi)        &&   // DMI alcista
                 (bodyR >= InpBodyThresh) &&
                 (close1 > open1);       // vela alcista

   // 8d. Evaluar señal SHORT
   bool shortOK = IsLLLH(1)          &&  // estructura bajista
                  (close1 < ema)     &&  // bajo EMA
                  (ndi > pdi)        &&  // DMI bajista
                  (bodyR >= InpBodyThresh) &&
                  (close1 < open1);      // vela bajista

   // Determinar signal final y bloqueos
   if(!longOK && !shortOK)
   {
      // Detectar razón específica para logging
      string blockReason = "signal_no_match";
      if(bodyR < InpBodyThresh)
         blockReason = "body_filter";
      else if(!IsHHHL(1) && !IsLLLH(1))
         blockReason = "structure_filter";
      else
         blockReason = "dmi_filter";

      PrintFormat("[DECISION_BLOCKED] reason=%s symbol=%s score=%.3f body=%.2f adx=%.1f",
                  blockReason, _Symbol, tz.score, bodyR, adx);

      logger.SignalEvalTZ(
         _Symbol, candidateDirS, h4Signal,
         tz.mode, tz.score, atr, dist,
         "", tz.rule_version,
         blockReason, cb.IsOperational(), cb.CurrentDrawdown()
      );
      return;
   }

   // ── 9. Cohort y dirección confirmada ────────────────────────────
   int    direction   = longOK ? 1 : -1;
   string directionS  = longOK ? "BUY" : "SELL";
   string cohort      = tzEngine.GetCohort(tz.tier, direction);

   PrintFormat("[ENTRY_COHORT] cohort=%s score=%.3f tier=%s symbol=%s",
               cohort, tz.score, tz.mode, _Symbol);

   // ── 10. ML Veto — shadow mode ────────────────────────────────────
   double mlScore = MLVetoShadowScore(tz.score, adx, bodyR);
   PrintFormat("[ML_VETO_SHADOW] score=%.3f decision=allow symbol=%s cohort=%s",
               mlScore, _Symbol, cohort);

   // ── 11. Calcular SL / TP / Lotes ─────────────────────────────────
   double askPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bidPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double slDist = atr * InpAtrSL;
   double tpDist = atr * InpAtrTP;

   double entryPrice, sl, tp;
   ENUM_ORDER_TYPE orderType;

   if(longOK)
   {
      orderType  = ORDER_TYPE_BUY;
      entryPrice = askPrice;
      sl = NormalizeDouble(entryPrice - slDist, _Digits);
      tp = NormalizeDouble(entryPrice + tpDist, _Digits);
   }
   else
   {
      orderType  = ORDER_TYPE_SELL;
      entryPrice = bidPrice;
      sl = NormalizeDouble(entryPrice + slDist, _Digits);
      tp = NormalizeDouble(entryPrice - tpDist, _Digits);
   }

   double lots = CalcLots(slDist);

   PrintFormat("[ENTRY_ACCEPTED] cohort=%s dir=%s lots=%.4f sl=%.5f tp=%.5f score=%.3f",
               cohort, directionS, lots, sl, tp, tz.score);

   // ── 12. Enviar signal_eval antes de ejecutar ─────────────────────
   logger.SignalEvalTZ(
      _Symbol, directionS, direction,
      tz.mode, tz.score, atr, dist,
      cohort, tz.rule_version,
      "", cb.IsOperational(), cb.CurrentDrawdown()
   );

   // ── 13. Ejecutar orden ───────────────────────────────────────────
   bool sent = false;
   if(orderType == ORDER_TYPE_BUY)
      sent = trade.Buy (lots, _Symbol, entryPrice, sl, tp, "v4321 " + cohort);
   else
      sent = trade.Sell(lots, _Symbol, entryPrice, sl, tp, "v4321 " + cohort);

   if(sent && trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      ulong ticket = trade.ResultOrder();
      logger.TradeOpenTZ(
         ticket, directionS, trade.ResultPrice(), lots, sl, tp,
         cb.CurrentDrawdown(),
         cohort, tz.score, tz.mode, atr, tz.rule_version
      );
      PrintFormat("TRADE | %s | ticket=%I64u | cohort=%s | entry=%.5f | sl=%.5f | tp=%.5f | lots=%.4f | score=%.3f",
                  directionS, ticket, cohort, trade.ResultPrice(), sl, tp, lots, tz.score);
   }
   else
   {
      PrintFormat("ORDEN RECHAZADA | retcode=%d | %s | cohort=%s",
                  trade.ResultRetcode(), trade.ResultComment(), cohort);
   }
}
