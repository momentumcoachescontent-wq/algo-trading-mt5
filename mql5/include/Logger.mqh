//+------------------------------------------------------------------+
//|  Logger.mqh                                                      |
//|  Envío de eventos de trading al webhook Cloudflare Worker.       |
//|  Versión: 2.0  |  Fase: F4  |  Fecha: 2026-04-10               |
//+------------------------------------------------------------------+
//  WHY:  Trazabilidad completa de cada evento del EA en Supabase.
//        Logger es best-effort: si el Worker no responde el EA
//        sigue operando sin interrupción. NUNCA bloquear el trading
//        por un fallo de logging.
//
//  PREREQUISITO MT5:
//    Tools → Options → Expert Advisors → Allow WebRequest:
//    https://algo-trading-mt5.momentumcoaches-content.workers.dev
//
//  Payload JSON enviado al Worker (POST /trading/webhook):
//    {
//      "event":       "open" | "close" | "init" | "circuit_break",
//      "ticket":      <int>,
//      "symbol":      "USDJPY",
//      "direction":   "BUY" | "SELL",
//      "open_price":  <double>,
//      "close_price": <double | null>,
//      "lots":        <double>,
//      "sl":          <double>,
//      "tp":          <double>,
//      "pnl":         <double | null>,
//      "ea_version":  "v2.3",
//      "phase":       "F4"
//    }
//+------------------------------------------------------------------+
#ifndef __LOGGER_MQH__
#define __LOGGER_MQH__

class CLogger
{
private:
   bool   m_enabled;
   string m_eaVersion;
   string m_url;
   string m_webhookSecret;
   long   m_magic;

   //--- Envía payload JSON al Worker; retorna true si HTTP 200
   bool SendEvent(string jsonPayload)
   {
      if(!m_enabled || m_url == "")
         return false;

      char   postData[];
      char   result[];
      string resultHeaders;

      StringToCharArray(jsonPayload, postData, 0, StringLen(jsonPayload));

      string headers = "Content-Type: application/json\r\n"
                       "X-EA-Secret: " + m_webhookSecret + "\r\n";

      int timeout = 8000;  // 8 segundos (margen para cold start del Worker)
      int httpCode = WebRequest(
         "POST",
         m_url + "/trading/webhook",
         headers,
         timeout,
         postData,
         result,
         resultHeaders
      );

      if(httpCode == 200)
         return true;

      // Log local sin bloquear
      PrintFormat("[LOGGER] WebRequest error | HTTP=%d | payload=%s", httpCode, jsonPayload);
      return false;
   }

   //--- Construye JSON base con metadatos del EA
   string BaseJson(string eventType, ulong ticket, string symbol,
                   string direction, double openPrice, double closePrice,
                   double lots, double sl, double tp, double pnl)
   {
      string hasClose = (closePrice > 0) ? DoubleToString(closePrice, 5) : "null";
      string hasPnl   = (pnl != 0 || eventType == "close")
                           ? DoubleToString(pnl, 2) : "null";

      return StringFormat(
         "{\"event\":\"%s\",\"ticket\":%I64u,\"symbol\":\"%s\","
         "\"direction\":\"%s\",\"open_price\":%.5f,\"close_price\":%s,"
         "\"lots\":%.4f,\"sl\":%.5f,\"tp\":%.5f,\"pnl\":%s,"
         "\"ea_version\":\"%s\",\"phase\":\"F4\"}",
         eventType, ticket, symbol,
         direction, openPrice, hasClose,
         lots, sl, tp, hasPnl,
         m_eaVersion
      );
   }

public:
   CLogger()
   {
      m_enabled       = false;
      m_eaVersion     = "v2.3";
      m_url           = "https://algo-trading-mt5.momentumcoaches-content.workers.dev";
      m_webhookSecret = "";
      m_magic         = 0;
   }

   void Init(string webhookSecret, long magic, string eaVersion = "v2.3",
             bool enabled = true, string url = "")
   {
      m_webhookSecret = webhookSecret;
      m_magic         = magic;
      m_eaVersion     = eaVersion;
      m_enabled       = enabled;
      m_url           = (url != "") ? url
                        : "https://algo-trading-mt5.momentumcoaches-content.workers.dev";

      PrintFormat("[LOGGER] Init | version=%s | enabled=%s | url=%s",
                  m_eaVersion, m_enabled ? "true" : "false", m_url);
   }

   //--- EA arrancó (sin trade asociado, ticket=0)
   void EAInit(double initialBalance)
   {
      PrintFormat("[LOGGER] EAInit | version=%s | balance=%.2f", m_eaVersion, initialBalance);

      string json = StringFormat(
         "{\"event\":\"init\",\"ticket\":0,\"symbol\":\"%s\","
         "\"direction\":\"NONE\",\"open_price\":0,\"close_price\":null,"
         "\"lots\":0,\"sl\":0,\"tp\":0,\"pnl\":null,"
         "\"ea_version\":\"%s\",\"phase\":\"F4\"}",
         _Symbol, m_eaVersion
      );
      SendEvent(json);
   }

   void EADeinit(int reason)
   {
      PrintFormat("[LOGGER] EADeinit | reason=%d", reason);
   }

   //--- Circuit breaker activado
   void CircuitBreak(double drawdownPct)
   {
      PrintFormat("[LOGGER] CircuitBreak | dd=%.2f%%", drawdownPct);

      string json = StringFormat(
         "{\"event\":\"circuit_break\",\"ticket\":0,\"symbol\":\"%s\","
         "\"direction\":\"NONE\",\"open_price\":0,\"close_price\":null,"
         "\"lots\":0,\"sl\":0,\"tp\":0,\"pnl\":null,"
         "\"ea_version\":\"%s\",\"phase\":\"F4\"}",
         _Symbol, m_eaVersion
      );
      SendEvent(json);
   }

   //--- Trade abierto
   void TradeOpen(ulong ticket, string direction, double entryPrice,
                  double volume, double sl, double tp, double drawdownPct)
   {
      PrintFormat("[LOGGER] TradeOpen | ticket=%I64u | dir=%s | entry=%.5f | vol=%.2f | sl=%.5f | tp=%.5f | dd=%.2f%%",
                  ticket, direction, entryPrice, volume, sl, tp, drawdownPct);

      string json = BaseJson("open", ticket, _Symbol, direction,
                             entryPrice, 0, volume, sl, tp, 0);
      SendEvent(json);
   }

   //--- Trade cerrado
   void TradeClose(ulong deal, string direction, double price,
                   double volume, double pnl, double drawdownPct)
   {
      PrintFormat("[LOGGER] TradeClose | deal=%I64u | dir=%s | price=%.5f | vol=%.2f | pnl=%.2f | dd=%.2f%%",
                  deal, direction, price, volume, pnl, drawdownPct);

      // Para close: open_price=0 (no disponible aquí), close_price=price
      string json = BaseJson("close", deal, _Symbol, direction,
                             0, price, volume, 0, 0, pnl);
      SendEvent(json);
   }
};

#endif
