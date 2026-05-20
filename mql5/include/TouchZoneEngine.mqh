//+------------------------------------------------------------------+
//|  TouchZoneEngine.mqh                                             |
//|  Sistema 3-tier de scoring precio–EMA en unidades ATR.           |
//|  Versión: v1.0  |  Fecha: 2026-05-20                            |
//+------------------------------------------------------------------+
//  Tiers:
//    EXACT    [0, exact_max]          → score 1.0        entrada viva
//    SOFT     [exact_max, soft_max]   → score 0.5–1.0    entrada viva
//    EXTENDED [soft_max, extended_max]→ score 0.0–0.5    ledger only
//    NONE     [> extended_max]        → score 0.0        ignorar
//
//  El soft_max (default 0.50 ATR) es el gate de entrada viva —
//  equivalente exacto al InpTouchMult = 0.50 de v2.3 (binary gate).
//+------------------------------------------------------------------+
#ifndef __TOUCHZONEENGINE_MQH__
#define __TOUCHZONEENGINE_MQH__

//--- Tier enum
enum TOUCH_ZONE_TIER
{
   TOUCH_EXACT    = 0,
   TOUCH_SOFT     = 1,
   TOUCH_EXTENDED = 2,
   TOUCH_NONE     = 3
};

//--- Resultado de evaluación
struct TouchZoneResult
{
   TOUCH_ZONE_TIER tier;
   double          score;          // 0.0 – 1.0
   string          mode;           // "exact" | "soft" | "extended" | "none"
   bool            is_live_entry;  // true si tier == EXACT o SOFT
   string          rule_version;
};

//--- Buffer de oportunidades extended
#define TZ_LEDGER_SIZE 20

struct OpportunityRecord
{
   datetime bar_time;
   string   symbol;
   int      candidate_dir;    // 1=LONG, -1=SHORT, 0=UNDECIDED
   double   touch_score;
   double   atr_value;
   double   ema_dist_atr;
   string   touch_zone_mode;
};

//+------------------------------------------------------------------+
class CTouchZoneEngine
{
private:
   double m_exactMax;
   double m_softMax;
   double m_extendedMax;
   string m_ruleVersion;

   OpportunityRecord m_ledger[TZ_LEDGER_SIZE];
   int               m_ledgerHead;
   int               m_ledgerCount;

public:
   CTouchZoneEngine()
   {
      m_exactMax    = 0.25;
      m_softMax     = 0.50;
      m_extendedMax = 1.50;
      m_ruleVersion = "v1.0";
      m_ledgerHead  = 0;
      m_ledgerCount = 0;
   }

   void Init(double exactMax = 0.25, double softMax = 0.50, double extendedMax = 1.50)
   {
      m_exactMax    = exactMax;
      m_softMax     = softMax;
      m_extendedMax = extendedMax;
      m_ledgerHead  = 0;
      m_ledgerCount = 0;
      PrintFormat("[TOUCH_ZONE_ENGINE] Init | exact=%.2f soft=%.2f extended=%.2f version=%s",
                  m_exactMax, m_softMax, m_extendedMax, m_ruleVersion);
   }

   //--- Evalúa distancia (en unidades ATR) y retorna tier + score
   TouchZoneResult Evaluate(double dist)
   {
      TouchZoneResult r;
      r.rule_version = m_ruleVersion;

      if(dist <= m_exactMax)
      {
         r.tier         = TOUCH_EXACT;
         r.score        = 1.0;
         r.mode         = "exact";
         r.is_live_entry = true;
      }
      else if(dist <= m_softMax)
      {
         double range   = m_softMax - m_exactMax;
         double frac    = (range > 0) ? (dist - m_exactMax) / range : 1.0;
         r.tier         = TOUCH_SOFT;
         r.score        = 1.0 - frac * 0.5;   // 1.0 → 0.5
         r.mode         = "soft";
         r.is_live_entry = true;
      }
      else if(dist <= m_extendedMax)
      {
         double range   = m_extendedMax - m_softMax;
         double frac    = (range > 0) ? (dist - m_softMax) / range : 1.0;
         r.tier         = TOUCH_EXTENDED;
         r.score        = 0.5 - frac * 0.5;   // 0.5 → 0.0
         r.mode         = "extended";
         r.is_live_entry = false;
      }
      else
      {
         r.tier         = TOUCH_NONE;
         r.score        = 0.0;
         r.mode         = "none";
         r.is_live_entry = false;
      }

      return r;
   }

   //--- Cohort label para trades vivos
   string GetCohort(TOUCH_ZONE_TIER tier, int direction)
   {
      string dirStr  = (direction == 1) ? "LONG" : "SHORT";
      string tierStr = (tier == TOUCH_EXACT) ? "EXACT" : "SOFT";
      return tierStr + "_PULLBACK_" + dirStr;
   }

   //--- Agrega candidato extended al ledger circular
   void LedgerAdd(datetime barTime, string symbol, int candidateDir,
                  double score, double atrValue, double distAtr)
   {
      m_ledger[m_ledgerHead].bar_time       = barTime;
      m_ledger[m_ledgerHead].symbol         = symbol;
      m_ledger[m_ledgerHead].candidate_dir  = candidateDir;
      m_ledger[m_ledgerHead].touch_score    = score;
      m_ledger[m_ledgerHead].atr_value      = atrValue;
      m_ledger[m_ledgerHead].ema_dist_atr   = distAtr;
      m_ledger[m_ledgerHead].touch_zone_mode = "extended";

      m_ledgerHead  = (m_ledgerHead + 1) % TZ_LEDGER_SIZE;
      if(m_ledgerCount < TZ_LEDGER_SIZE) m_ledgerCount++;
   }

   int    LedgerCount()  const { return m_ledgerCount; }
   string RuleVersion()  const { return m_ruleVersion; }
   double SoftMaxATR()   const { return m_softMax; }
};

#endif
