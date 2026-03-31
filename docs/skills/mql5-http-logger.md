---
name: mql5-http-logger
description: Send HTTP POST requests from MQL5 EAs to Cloudflare Workers or any webhook endpoint. Use this skill when implementing trade logging, alerts, or any external HTTP call from an Expert Advisor. Covers WebRequest setup, MT5 whitelist requirement, JSON payload construction, and error handling. Always use this skill before writing any WebRequest code in MQL5.
---

# MQL5 HTTP Logger

## PASO OBLIGATORIO antes de usar WebRequest

En MT5 → Tools → Options → Expert Advisors → "Allow WebRequest for listed URL":
Agregar: `https://algo-trading-mt5.momentumcoaches-content.workers.dev`

Sin este paso, WebRequest retorna error -1 silenciosamente.

## Función de envío al Worker

```mql5
void LogTradeEvent(string eventType, ulong ticket,
                   double openPrice, double sl, double tp,
                   double lots,     double pnl = 0) {

   string url     = "https://algo-trading-mt5.momentumcoaches-content.workers.dev/trading/webhook";
   string secret  = "TU_EA_WEBHOOK_SECRET";  // mismo valor que en CF secret

   // Construir JSON manualmente (MQL5 no tiene JSON nativo)
   string payload = StringFormat(
      "{\"event\":\"%s\","
      "\"ticket\":%d,"
      "\"symbol\":\"%s\","
      "\"direction\":\"%s\","
      "\"open_price\":%.5f,"
      "\"lots\":%.2f,"
      "\"sl\":%.5f,"
      "\"tp\":%.5f,"
      "\"pnl\":%.2f,"
      "\"ea_version\":\"v1\","
      "\"phase\":\"P0\"}",
      eventType,
      (int)ticket,
      _Symbol,
      (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "buy" : "sell"),
      openPrice, lots, sl, tp, pnl
   );

   // Headers
   string headers = "Content-Type: application/json\r\n"
                    "X-EA-Secret: " + secret + "\r\n";

   char   postData[];
   char   result[];
   string resultHeaders;

   StringToCharArray(payload, postData, 0, StringLen(payload));

   int httpCode = WebRequest(
      "POST",          // method
      url,             // url
      headers,         // headers
      5000,            // timeout ms
      postData,        // body
      result,          // response body
      resultHeaders    // response headers
   );

   if(httpCode == 200) {
      Print("LOG OK: ", eventType, " ticket=", ticket);
   } else if(httpCode == -1) {
      Print("LOG ERROR: URL no whitelisted en MT5 Options");
   } else {
      Print("LOG ERROR HTTP ", httpCode, ": ", CharArrayToString(result));
   }
}
```

## Cuándo llamar LogTradeEvent

```mql5
// Al abrir trade — después de trade.Buy/Sell exitoso:
if(trade.ResultRetcode() == TRADE_RETCODE_DONE) {
   LogTradeEvent("trade_open",
      trade.ResultOrder(),
      entryPrice, sl, tp, lots);
}

// Al cerrar (en OnTradeTransaction o verificando posiciones):
LogTradeEvent("trade_close",
   ticket, openPrice, sl, tp, lots, pnl);

// Circuit breaker activado:
LogTradeEvent("circuit_break", 0, 0, 0, 0, 0);
```

## OnTradeTransaction — detectar cierre automático

```mql5
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result) {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) {
      if(trans.deal_type == DEAL_TYPE_BUY ||
         trans.deal_type == DEAL_TYPE_SELL) {
         // posición cerrada por SL o TP
         double pnl = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         LogTradeEvent("trade_close",
            trans.order, trans.price, 0, 0,
            trans.volume, pnl);
      }
   }
}
```

## Reglas críticas
- WebRequest es BLOQUEANTE — no llamar dentro de OnTick sin IsNewBar
- Timeout = 5000ms máximo para no frenar el EA
- Si el Worker no responde, el EA sigue funcionando (log es best-effort)
- El secret NUNCA va en el repo — solo en el archivo .mq5 local
