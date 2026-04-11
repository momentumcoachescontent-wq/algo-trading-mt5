//+------------------------------------------------------------------+
//|  EMA_ADX_Pullback_v23.mq5                                        |
//|  Expert Advisor v2.3 — EMA21 Pullback + ADX14 + ATR sizing      |
//|  Símbolo principal: USDJPY  |  Timeframe: H4                    |
//|  Versión: 2.3.0   |  Fase: F4   |  Fecha: 2026-04-10           |
//+------------------------------------------------------------------+
//
//  ESTRATEGIA (espejo exacto de python/research/signals.py):
//    Señal LONG  (todos los filtros sobre barra[1] — ya cerrada):
//      1. HH/HL  : estructura de máximos y mínimos crecientes (lookback=50)
//      2. Touch   : close[1] > ema21[1] Y |close[1]-ema21[1]| / atr[1] ≤ 0.5
//      3. ADX     : adx[1] ≥ 25
//      4. DMI     : +DI[1] > -DI[1]
//      5. Body    : body_ratio[1] ≥ 0.40 (vela con cuerpo real)
//      6. Alcista : close[1] > open[1]
//
//    Señal SHORT : espejo inverso (estructura LL/LH, bajo EMA, -DI > +DI, bajista)
//
//    SL = 1.5 × ATR[1]  desde precio de entrada
//    TP = 2.5 × ATR[1]  desde precio de entrada   (R:R = 1:1.67)
//    Riesgo = 1% del balance por operación
//    Una sola posición abierta a la vez
//    Entrada solo en apertura de nueva vela H4
//
//  CAMBIO vs v1 (EMA_ADX_v1):
//    v1  = EMA21/50 crossover
//    v2.3 = EMA21 pullback touch + HH/HL structure + body filter
//
//  DEPENDENCIAS:
//    • Include/CircuitBreaker.mqh  — kill-switch 5% drawdown
//    • Include/Logger.mqh          — webhook Cloudflare Worker (F4)
//    • <Trade\Trade.mqh>           — CTrade librería estándar
//
//  PRIMERA EJECUCIÓN:
//    1. Copiar EMA_ADX_Pullback_v23.mq5 → MQL5/Experts/
//    2. Copiar Include/*.mqh             → MQL5/Include/
//    3. Compilar (F7)
//    4. MT5 → Options → Expert Advisors → WebRequest →
//       añadir: https://algo-trading-mt5.momentumcoaches-content.workers.dev
//    5. Adjuntar en gráfico USDJPY H4 con "Allow live trading" ✓
//+------------------------------------------------------------------+

#include <Trade\Trade.mqh>
#include <CircuitBreaker.mqh>
#include <Logger.mqh>

//--- Parámetros de entrada

input group   "=== IDENTIFICACIÓN ==="
input int     InpMagic         = 20260410;    // Magic Number único por EA/cuenta
input string  InpEAVersion     = "v2.3";      // Versión para logging

input group   "=== WEBHOOK ==="
input string  InpWebhookSecret = "";          // Secret X-EA-Secret (del .env)
input bool    InpWebhookEnable = true;        // Activar envío al Worker

input group   "=== INDICADORES ==="
input int     InpEmaPeriod     = 21;          // EMA período
input int     InpAdxPeriod     = 14;          // ADX período
input double  InpAdxMin        = 25.0;        // ADX mínimo (filtro de tendencia)
input int     InpAtrPeriod     = 14;          // ATR período
input double  InpTouchMult     = 0.5;         // Máx distancia EMA en unidades ATR

input group   "=== SEÑAL ==="
input double  InpBodyThresh    = 0.40;        // Body ratio mínimo (0.40 = 40%)
input int     InpLookback      = 50;          // Ventana HH/HL estructura

input group   "=== GESTIÓN DE RIESGO ==="
input double  InpRisk          = 1.0;         // Riesgo por trade (% balance)
input double  InpAtrSL         = 1.5;         // SL = N × ATR
input double  InpAtrTP         = 2.5;         // TP = N × ATR
input double  InpKillDD        = 5.0;         // Circuit breaker drawdown %

//--- Objetos globales
CTrade          trade;
CCircuitBreaker cb;
CLogger         logger;

//--- Handles de indicadores
int    hEma;
int    hAdx;
int    hAtr;
datetime lastBarTime = 0;


//+------------------------------------------------------------------+
//|  Helpers — lectura de buffers                                     |
//+------------------------------------------------------------------+

double GetEMA(int shift)  { double b[1]; CopyBuffer(hEma, 0, shift, 1, b); return b[0]; }
double GetATR(int shift)  { double b[1]; CopyBuffer(hAtr, 0, shift, 1, b); return b[0]; }
double GetADX(int shift)  { double b[1]; CopyBuffer(hAdx, 0, shift, 1, b); return b[0]; }
double GetPDI(int shift)  { double b[1]; CopyBuffer(hAdx, 1, shift, 1, b); return b[0]; }
double GetNDI(int shift)  { double b[1]; CopyBuffer(hAdx, 2, shift, 1, b); return b[0]; }

//--- Precio OHLC de barra[shift]
double GetClose(int shift) { double b[1]; CopyClose(_Symbol, PERIOD_CURRENT, shift, 1, b); return b[0]; }
double GetOpen(int shift)  { double b[1]; CopyOpen(_Symbol,  PERIOD_CURRENT, shift, 1, b); return b[0]; }
double GetHigh(int shift)  { double b[1]; CopyHigh(_Symbol,  PERIOD_CURRENT, shift, 1, b); return b[0]; }
double GetLow(int shift)   { double b[1]; CopyLow(_Symbol,   PERIOD_CURRENT, shift, 1, b); return b[0]; }

//--- Detecta estructura HH/HL (ventana actual vs ventana anterior, lookback barras)
bool IsHHHL(int refShift = 1)
{
   int start = refShift; // barra[1] = última cerrada

   double highs[];
   double lows[];

   // Necesitamos 2 × lookback barras desde refShift
   int barsNeeded = InpLookback * 2 + start;
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows,  true);
   if(CopyHigh(_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, highs) <= 0) return false;
   if(CopyLow (_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, lows)  <= 0) return false;

   // Ventana actual: barras [start .. start+lookback-1]
   // Ventana prev:   barras [start+lookback .. start+2*lookback-1]
   double currHigh = -DBL_MAX, currLow = DBL_MAX;
   double prevHigh = -DBL_MAX, prevLow = DBL_MAX;

   for(int i = start; i < start + InpLookback; i++)
   {
      if(highs[i] > currHigh) currHigh = highs[i];
      if(lows[i]  < currLow)  currLow  = lows[i];
   }
   for(int i = start + InpLookback; i < start + InpLookback * 2; i++)
   {
      if(highs[i] > prevHigh) prevHigh = highs[i];
      if(lows[i]  < prevLow)  prevLow  = lows[i];
   }

   return (currHigh > prevHigh) && (currLow > prevLow);
}

//--- Detecta estructura LL/LH (espejo bajista)
bool IsLLLH(int refShift = 1)
{
   int start = refShift;
   double highs[];
   double lows[];

   int barsNeeded = InpLookback * 2 + start;
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows,  true);
   if(CopyHigh(_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, highs) <= 0) return false;
   if(CopyLow (_Symbol, PERIOD_CURRENT, 0, barsNeeded + 1, lows)  <= 0) return false;

   double currHigh = -DBL_MAX, currLow = DBL_MAX;
   double prevHigh = -DBL_MAX, prevLow = DBL_MAX;

   for(int i = start; i < start + InpLookback; i++)
   {
      if(highs[i] > currHigh) currHigh = highs[i];
      if(lows[i]  < currLow)  currLow  = lows[i];
   }
   for(int i = start + InpLookback; i < start + InpLookback * 2; i++)
   {
      if(highs[i] > prevHigh) prevHigh = highs[i];
      if(lows[i]  < prevLow)  prevLow  = lows[i];
   }

   return (currHigh < prevHigh) && (currLow < prevLow);
}

//--- Body ratio de barra[shift]
double BodyRatio(int shift)
{
   double o = GetOpen(shift);
   double c = GetClose(shift);
   double h = GetHigh(shift);
   double l = GetLow(shift);
   double range = h - l;
   if(range <= 0.0) return 0.0;
   return MathAbs(c - o) / range;
}

//--- Calcula lote basado en % riesgo
double CalcLots(double slPoints)
{
   if(slPoints <= 0.0) return 0.01;

   double balance    = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmt    = balance * (InpRisk / 100.0);
   double tickValue  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double lotStep    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(tickValue <= 0.0 || tickSize <= 0.0) return minLot;

   double valuePerPoint = tickValue / tickSize;
   double lots = riskAmt / (slPoints / _Point * valuePerPoint);

   // Redondear al step más cercano hacia abajo
   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(lots, minLot);
   lots = MathMin(lots, maxLot);

   return lots;
}

//--- Verifica si ya hay posición abierta con nuestro Magic
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionSelectByTicket(PositionGetTicket(i)))
      {
         if(PositionGetInteger(POSITION_MAGIC) == InpMagic &&
            PositionGetString(POSITION_SYMBOL) == _Symbol)
            return true;
      }
   }
   return false;
}


//+------------------------------------------------------------------+
//|  OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(10);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   hEma = iMA(_Symbol,  PERIOD_CURRENT, InpEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   hAdx = iADX(_Symbol, PERIOD_CURRENT, InpAdxPeriod);
   hAtr = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);

   if(hEma == INVALID_HANDLE || hAdx == INVALID_HANDLE || hAtr == INVALID_HANDLE)
   {
      Print("❌ ERROR: No se pudo crear indicadores");
      return INIT_FAILED;
   }

   cb.Init(InpKillDD);

   logger.Init(InpWebhookSecret, InpMagic, InpEAVersion, InpWebhookEnable);
   logger.EAInit(cb.GetInitialBalance());

   PrintFormat("✅ EA v2.3 iniciado | %s %s | Magic=%d | Risk=%.1f%%",
               _Symbol, EnumToString(PERIOD_CURRENT), InpMagic, InpRisk);
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
//|  OnTrade — detecta cierre de posición y loguea                   |
//+------------------------------------------------------------------+
void OnTrade()
{
   // Revisar historial de deals recientes para capturar cierres
   HistorySelect(TimeCurrent() - 60, TimeCurrent());

   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0) continue;

      long magic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
      if(magic != InpMagic) continue;

      long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
      if(entryType != DEAL_ENTRY_OUT) continue; // solo cierres

      string dir    = (HistoryDealGetInteger(dealTicket, DEAL_TYPE) == DEAL_TYPE_BUY) ? "BUY" : "SELL";
      double price  = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
      double volume = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
      double pnl    = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
      double dd     = cb.CurrentDrawdown();

      logger.TradeClose(dealTicket, dir, price, volume, pnl, dd);
      break; // solo el más reciente
   }
}


//+------------------------------------------------------------------+
//|  OnTick — lógica principal (una vez por vela nueva)              |
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
   double ema   = GetEMA(1);
   double atr   = GetATR(1);
   double adx   = GetADX(1);
   double pdi   = GetPDI(1);
   double ndi   = GetNDI(1);
   double close1 = GetClose(1);
   double open1  = GetOpen(1);

   if(atr <= 0.0) return;

   double touchDist = MathAbs(close1 - ema) / atr;
   double bodyR     = BodyRatio(1);

   // ── 5. Filtro ADX ───────────────────────────────────────────────
   if(adx < InpAdxMin) return;

   // ── 6. Evaluar señal LONG ────────────────────────────────────────
   bool longOK = IsHHHL(1)          &&   // estructura HH/HL
                 (close1 > ema)     &&   // precio sobre EMA
                 (touchDist <= InpTouchMult) && // touch de EMA
                 (pdi > ndi)        &&   // DMI alcista
                 (bodyR >= InpBodyThresh) && // body confirm
                 (close1 > open1);       // vela alcista

   // ── 7. Evaluar señal SHORT ───────────────────────────────────────
   bool shortOK = IsLLLH(1)         &&   // estructura LL/LH
                  (close1 < ema)    &&   // precio bajo EMA
                  (touchDist <= InpTouchMult) && // touch de EMA
                  (ndi > pdi)       &&   // DMI bajista
                  (bodyR >= InpBodyThresh) && // body confirm
                  (close1 < open1);      // vela bajista

   if(!longOK && !shortOK) return;

   // ── 8. Calcular SL / TP / Lotes ─────────────────────────────────
   double askPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bidPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double slDist = atr * InpAtrSL;
   double tpDist = atr * InpAtrTP;

   double entryPrice, sl, tp;
   string direction;
   ENUM_ORDER_TYPE orderType;

   if(longOK)
   {
      direction = "BUY";
      orderType = ORDER_TYPE_BUY;
      entryPrice = askPrice;
      sl = NormalizeDouble(entryPrice - slDist, _Digits);
      tp = NormalizeDouble(entryPrice + tpDist, _Digits);
   }
   else
   {
      direction = "SELL";
      orderType = ORDER_TYPE_SELL;
      entryPrice = bidPrice;
      sl = NormalizeDouble(entryPrice + slDist, _Digits);
      tp = NormalizeDouble(entryPrice - tpDist, _Digits);
   }

   double lots = CalcLots(slDist);

   // ── 9. Ejecutar orden ────────────────────────────────────────────
   bool sent = false;
   if(orderType == ORDER_TYPE_BUY)
      sent = trade.Buy(lots, _Symbol, entryPrice, sl, tp, "v2.3 LONG");
   else
      sent = trade.Sell(lots, _Symbol, entryPrice, sl, tp, "v2.3 SHORT");

   if(sent && trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      ulong ticket = trade.ResultOrder();
      double dd    = cb.CurrentDrawdown();
      logger.TradeOpen(ticket, direction, trade.ResultPrice(), lots, sl, tp, dd);

      PrintFormat("✅ %s | ticket=%I64u | entry=%.5f | sl=%.5f | tp=%.5f | lots=%.4f | atr=%.5f",
                  direction, ticket, trade.ResultPrice(), sl, tp, lots, atr);
   }
   else
   {
      PrintFormat("⚠️  Orden rechazada | retcode=%d | %s", trade.ResultRetcode(), trade.ResultComment());
   }
}
