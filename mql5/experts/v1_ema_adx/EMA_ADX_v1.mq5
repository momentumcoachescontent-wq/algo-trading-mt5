//+------------------------------------------------------------------+
//|  EMA_ADX_v1.mq5                                                  |
//|  Expert Advisor v1 — EMA21/50 cruce + ADX filtro + ATR sizing   |
//|  Símbolo: EURUSD  |  Timeframe: H1                               |
//|  Versión: 1.0.0   |  Fase: F2   |  Fecha: 2026-03-31            |
//+------------------------------------------------------------------+
//
//  ESTRATEGIA:
//    • Señal LONG  : EMA21 cruza ARRIBA de EMA50 + ADX(14) > 25
//    • Señal SHORT : EMA21 cruza ABAJO de EMA50 + ADX(14) > 25
//    • SL = 1.5 × ATR(14)  desde el precio de entrada
//    • TP = 3.0 × ATR(14)  desde el precio de entrada  (R:R = 1:2)
//    • Tamaño = 1% del balance (riesgo fijo por operación)
//    • Una sola posición abierta a la vez
//    • Entrada solo en apertura de nueva vela H1
//
//  DEPENDENCIAS:
//    • Include/CircuitBreaker.mqh  — kill-switch 5% drawdown
//    • Include/Logger.mqh          — webhook Cloudflare Worker
//    • <Trade\Trade.mqh>           — CTrade de la librería estándar
//
//  PRIMERA EJECUCIÓN:
//    1. Copiar EMA_ADX_v1.mq5 → MQL5/Experts/
//    2. Copiar Include/*.mqh    → MQL5/Include/
//    3. Compilar (F7)
//    4. MT5 → Options → Expert Advisors → WebRequest → añadir URL del Worker
//    5. Adjuntar en gráfico EURUSD H1 con "Allow live trading" ✓
//+------------------------------------------------------------------+

#include <Trade\Trade.mqh>
#include <CircuitBreaker.mqh>
#include <Logger.mqh>

//--- Parámetros de entrada
input double  InpKillDD        = 5.0;
input string  InpWebhookSecret = "77440113982e0e5019010d5b1365f7f03f910d1316285";

input group   "=== IDENTIFICACIÓN ==="
input int     InpMagic      = 20260331; // Magic Number (único por EA/cuenta)

input group   "=== INDICADORES ==="
input int     InpEmaFast    = 21;       // EMA rápida (períodos)
input int     InpEmaSlow    = 50;       // EMA lenta  (períodos)
input int     InpAdxPeriod  = 14;       // ADX período
input double  InpAdxMin     = 25.0;     // ADX mínimo para filtrar tendencia
input int     InpAtrPeriod  = 14;       // ATR período

input group   "=== GESTIÓN DE RIESGO ==="
input double  InpRisk       = 1.0;      // Riesgo por trade (% sobre balance)
input double  InpAtrSL      = 1.5;      // SL = N × ATR
input double  InpAtrTP      = 3.0;      // TP = N × ATR  (R:R implícito = 2:1)

//--- Objetos globales
CTrade          trade;
CCircuitBreaker cb;
CLogger         logger;

int    handleEmaFast;
int    handleEmaSlow;
int    handleAdx;
int    handleAtr;
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
//|  OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit() {
   //--- Configurar CTrade
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(10);       // slippage tolerado: 1 pip
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   //--- Crear handles de indicadores
   handleEmaFast = iMA(_Symbol, PERIOD_CURRENT, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   handleEmaSlow = iMA(_Symbol, PERIOD_CURRENT, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   handleAdx     = iADX(_Symbol, PERIOD_CURRENT, InpAdxPeriod);
   handleAtr     = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);

   if(handleEmaFast == INVALID_HANDLE || handleEmaSlow == INVALID_HANDLE ||
      handleAdx     == INVALID_HANDLE || handleAtr     == INVALID_HANDLE) {
      Print("❌ ERROR: No se pudo crear uno o más indicadores");
      return INIT_FAILED;
   }

   //--- Inicializar circuit breaker
   cb.Init(InpKillDD);

   //--- Log de arranque (best-effort, no bloquea init)
   logger.Init(InpWebhookSecret, InpMagic, "v1.0.0", true);
   logger.EAInit(cb.GetInitialBalance());

   PrintFormat("✅ EA v1 iniciado | Símbolo=%s TF=%s Magic=%d Risk=%.1f%%",
               _Symbol, EnumToString(PERIOD_CURRENT), InpMagic, InpRisk);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//|  OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   logger.EADeinit(reason);
   IndicatorRelease(handleEmaFast);
   IndicatorRelease(handleEmaSlow);
   IndicatorRelease(handleAdx);
   IndicatorRelease(handleAtr);
   PrintFormat("EA detenido | reason=%d", reason);
}

//+------------------------------------------------------------------+
//|  OnTick — punto de entrada principal                              |
//+------------------------------------------------------------------+
void OnTick() {
   //--- 1. Circuit breaker — PRIMERA VERIFICACIÓN, siempre
   if(!cb.IsOperational()) {
      if(cb.IsTriggered())
         logger.CircuitBreak(cb.CurrentDrawdown()); // log una sola vez
      return;
   }

   //--- 2. Solo actuar en apertura de nueva vela
   if(!IsNewBar()) return;

   //--- 3. Leer indicadores (shift=1 → vela cerrada confirmada)
   double emaFast0 = GetBuffer(handleEmaFast, 0, 0);
   double emaFast1 = GetBuffer(handleEmaFast, 0, 1);
   double emaSlow0 = GetBuffer(handleEmaSlow, 0, 0);
   double emaSlow1 = GetBuffer(handleEmaSlow, 0, 1);
   double adx1     = GetBuffer(handleAdx,     0, 1);  // buffer 0 = ADX principal
   double atr1     = GetBuffer(handleAtr,     0, 1);

   //--- Validar que todos los buffers son válidos
   if(emaFast0 == EMPTY_VALUE || emaFast1 == EMPTY_VALUE ||
      emaSlow0 == EMPTY_VALUE || emaSlow1 == EMPTY_VALUE ||
      adx1     == EMPTY_VALUE || atr1     == EMPTY_VALUE) {
      Print("⚠️  Buffer(s) no disponibles — esperando datos suficientes");
      return;
   }

   //--- 4. Detectar señales
   bool bullCross = (emaFast1 < emaSlow1) && (emaFast0 > emaSlow0);
   bool bearCross = (emaFast1 > emaSlow1) && (emaFast0 < emaSlow0);
   bool trendOk   = (adx1 >= InpAdxMin);

   //--- 5. Lógica de entrada (solo si no hay posición abierta)
   if(!HasOpenPosition()) {
      if(bullCross && trendOk) {
         OpenTrade(ORDER_TYPE_BUY, atr1);
      } else if(bearCross && trendOk) {
         OpenTrade(ORDER_TYPE_SELL, atr1);
      }
   }
}

//+------------------------------------------------------------------+
//|  OnTradeTransaction — detecta cierres por SL/TP                  |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,
                        const MqlTradeResult      &res) {

   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

   //--- Solo nos interesan deals de cierre (DEAL_ENTRY_OUT)
   if(!HistoryDealSelect(trans.deal)) return;
   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT) return;

   double pnl    = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
   double vol    = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
   double price  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
   long   type   = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
   string dir    = (type == DEAL_TYPE_BUY) ? "buy" : "sell";

   logger.TradeClose(trans.deal, dir, price, vol, pnl, cb.CurrentDrawdown());

   PrintFormat("📊 CIERRE | PnL=%.2f | Lots=%.2f | Drawdown=%.2f%%",
               pnl, vol, cb.CurrentDrawdown());
}

//+------------------------------------------------------------------+
//|  Helpers                                                          |
//+------------------------------------------------------------------+

//--- IsNewBar: true solo en la primera tick de cada vela
bool IsNewBar() {
   datetime currentBar = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(currentBar != lastBarTime) {
      lastBarTime = currentBar;
      return true;
   }
   return false;
}

//--- GetBuffer: lectura segura con ArraySetAsSeries
double GetBuffer(int handle, int buffer, int shift) {
   double arr[];
   ArraySetAsSeries(arr, true);
   if(CopyBuffer(handle, buffer, 0, shift + 2, arr) < shift + 2)
      return EMPTY_VALUE;
   return arr[shift];
}

//--- HasOpenPosition: verifica si ya hay una posición de este EA en este símbolo
bool HasOpenPosition() {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(PositionGetSymbol(i)               == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
   }
   return false;
}

//--- CalculateSLTP: calcula SL y TP en precio basados en ATR
void CalculateSLTP(ENUM_ORDER_TYPE orderType, double atr,
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

//--- CalculateLots: sizing por % de riesgo fijo
double CalculateLots(double slPoints) {
   double balance      = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount   = balance * InpRisk / 100.0;
   double tickValue    = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize     = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double point        = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   double valuePerPt   = (tickSize > 0) ? tickValue * point / tickSize : 0;
   if(valuePerPt <= 0 || slPoints <= 0) {
      Print("❌ CalculateLots: valuePerPt o slPoints inválido");
      return 0;
   }

   double lots    = riskAmount / (slPoints * valuePerPt);
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));
   return NormalizeDouble(lots, 2);
}

//--- OpenTrade: construye y envía la orden completa
void OpenTrade(ENUM_ORDER_TYPE orderType, double atr) {
   double sl = 0, tp = 0;
   CalculateSLTP(orderType, atr, sl, tp);

   double entryPrice = (orderType == ORDER_TYPE_BUY)
      ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
      : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double slPoints = MathAbs(entryPrice - sl) / _Point;
   double lots     = CalculateLots(slPoints);

   if(lots <= 0) {
      Print("❌ OpenTrade abortada: lots=0");
      return;
   }

   string dir     = (orderType == ORDER_TYPE_BUY) ? "buy" : "sell";
   string comment = StringFormat("EA_v1_%s", dir);

   bool ok = (orderType == ORDER_TYPE_BUY)
      ? trade.Buy (lots, _Symbol, entryPrice, sl, tp, comment)
      : trade.Sell(lots, _Symbol, entryPrice, sl, tp, comment);

   if(ok && trade.ResultRetcode() == TRADE_RETCODE_DONE) {
      ulong ticket = trade.ResultOrder();
      PrintFormat("✅ APERTURA %s | Lots=%.2f | Entry=%.5f | SL=%.5f | TP=%.5f | ATR=%.5f",
                  StringToUpper(dir), lots, entryPrice, sl, tp, atr);
      logger.TradeOpen(ticket, dir, entryPrice, lots, sl, tp, cb.CurrentDrawdown());
   } else {
      PrintFormat("❌ ORDEN FALLIDA %s | Código=%d | %s",
                  StringToUpper(dir),
                  trade.ResultRetcode(),
                  trade.ResultRetcodeDescription());
   }
}
//+------------------------------------------------------------------+
//  FIN EMA_ADX_v1.mq5
//+------------------------------------------------------------------+
