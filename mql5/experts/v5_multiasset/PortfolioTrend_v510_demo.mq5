#property copyright "algo-trading-mt5"
#property version "5.100"
#property strict
#include <Trade/Trade.mqh>
#include "V5SignalCore.mqh"

// New experiment. DEMO/TESTER only. The default profile is the fixed hypothesis
// that remained positive in validation and retrospective audit at doubled costs.
// Other researched symbols/timeframes remain configurable through these inputs.
input group "=== CORE D1 ==="
input string InpSymbols="USDJPY,USDCHF,XAUUSD";
input ENUM_TIMEFRAMES InpTimeframe1=PERIOD_D1;
input int InpEntryLookback=20;
input int InpExitLookback=10;
input int InpTrendLookback=200;
input group "=== EXPERIMENTAL H4 ==="
input bool InpUseSecondTimeframe=true;
input string InpSecondSymbols="XAUUSD";
input ENUM_TIMEFRAMES InpTimeframe2=PERIOD_H4;
input int InpEntryLookback2=60;
input int InpExitLookback2=30;
input int InpTrendLookback2=600;
input group "=== DEMO EXECUTION ==="
input double InpLots=0.10; // Configurable demo volume; broker min/max/step still apply.
input ulong InpMagicBase=2026090500;
input bool InpEnableDemoOrders=true;
input int InpDeviationPoints=30;
input int InpPollSeconds=30;
input group "=== TELEMETRY (PRIVATE PRESET) ==="
input bool InpWebhookEnable=false;
input string InpWebhookURL="https://algo-trading-mt5-webhook.momentumcoaches-content.workers.dev/trading/webhook";
input string InpWebhookSecret="";
input int InpHeartbeatSeconds=900;

struct V5Slot
{
   string symbol;
   ENUM_TIMEFRAMES tf;
   int entryLookback;
   int exitLookback;
   int trendLookback;
   string sleeve;
   ulong magic;
   datetime lastbar;
};
V5Slot slots[];
CTrade trade;
int audit=INVALID_HANDLE;
datetime lastHeartbeat=0;
bool startupTelemetrySent=false;
string bootId="";
bool telemetryLeader=false;
string telemetryLeaderKey="";

bool EnsureTelemetryLeader()
{
   if((bool)MQLInfoInteger(MQL_TESTER) || !InpWebhookEnable || InpWebhookSecret=="")return false;
   if(telemetryLeaderKey=="")telemetryLeaderKey=StringFormat("V5_TELEMETRY_%I64d",AccountInfoInteger(ACCOUNT_LOGIN));
   datetime now=TimeLocal();
   if(telemetryLeader)
   {
      GlobalVariableSet(telemetryLeaderKey,(double)now);
      return true;
   }
   if(!GlobalVariableCheck(telemetryLeaderKey))GlobalVariableSet(telemetryLeaderKey,0);
   double previous=GlobalVariableGet(telemetryLeaderKey);
   int staleAfter=(int)MathMax(90,InpPollSeconds*4);
   if(previous>(double)(now-staleAfter))return false;
   if(!GlobalVariableSetOnCondition(telemetryLeaderKey,(double)now,previous))return false;
   telemetryLeader=true;
   PrintFormat("[V5_TELEMETRY_LEADER] boot=%s",bootId);
   return true;
}

string JsonEscape(string value)
{
   StringReplace(value,"\\","\\\\");
   StringReplace(value,"\"","\\\"");
   StringReplace(value,"\r"," ");
   StringReplace(value,"\n"," ");
   return value;
}

string IsoTime(const datetime value)
{
   string result=TimeToString(value,TIME_DATE|TIME_SECONDS);
   StringReplace(result,".","-");
   StringReplace(result," ","T");
   return result+"Z";
}

bool SendWebhook(const string payload)
{
   if((bool)MQLInfoInteger(MQL_TESTER) || !telemetryLeader || !InpWebhookEnable || InpWebhookURL=="" || InpWebhookSecret=="")return false;
   char postData[],result[];string resultHeaders;
   StringToCharArray(payload,postData,0,StringLen(payload),CP_UTF8);
   string headers="Content-Type: application/json\r\nX-EA-Secret: "+InpWebhookSecret+"\r\n";
   ResetLastError();
   int httpCode=WebRequest("POST",InpWebhookURL,headers,5000,postData,result,resultHeaders);
   if(httpCode==200)return true;
   PrintFormat("[V5_WEBHOOK_FAIL] http=%d | error=%d | response=%s",httpCode,GetLastError(),CharArrayToString(result));
   return false;
}

bool SendRuntimeTelemetry(const string runtimeEvent,const int reasonCode=-1)
{
   double balance=AccountInfoDouble(ACCOUNT_BALANCE);
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   double floating=equity-balance;
   string eventType=runtimeEvent=="deinit"?"ea_deinit":"ea_init";
   string payload=StringFormat(
      "{\"event\":\"%s\",\"runtime_event\":\"%s\",\"symbol\":\"USDJPY\","
      "\"ea_version\":\"v5.1.0\",\"phase\":\"V5_DEMO\",\"strategy_variant\":\"portfolio_trend_v510\","
      "\"execution_mode\":\"DEMO\",\"order_send_allowed\":true,\"capital_enabled\":false,"
      "\"execution_scope\":{\"mode\":\"DEMO\",\"order_send_allowed\":true,\"capital_enabled\":false,\"shadow_only\":false},"
      "\"boot_id\":\"%s\",\"terminal_time\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,"
      "\"floating_pnl\":%.2f,\"free_margin\":%.2f,\"leverage\":%d,\"open_positions\":%d,"
      "\"terminal_connected\":%s,\"terminal_trade_allowed\":%s,"
      "\"symbols\":\"%s\",\"timeframes\":\"D1,H4\",\"experimental_symbols\":\"%s\",\"deinit_reason_code\":%d}",
      eventType,JsonEscape(runtimeEvent),JsonEscape(bootId),IsoTime(TimeCurrent()),balance,equity,floating,
      AccountInfoDouble(ACCOUNT_MARGIN_FREE),(int)AccountInfoInteger(ACCOUNT_LEVERAGE),PositionsTotal(),
      TerminalInfoInteger(TERMINAL_CONNECTED)?"true":"false",TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)?"true":"false",
      JsonEscape(InpSymbols),JsonEscape(InpSecondSymbols),reasonCode);
   bool ok=SendWebhook(payload);
   PrintFormat("[V5_TELEMETRY_%s] runtime=%s",ok?"OK":"SKIP_OR_FAIL",runtimeEvent);
   return ok;
}

bool SendTradeTelemetry(const string eventType,const V5Slot &s,const string direction,
   const ulong orderTicket,const ulong dealTicket,const ulong positionId,const string signalId,
   const double openPrice,const double closePrice,const double lots,const double pnl,const datetime openTime=0)
{
   string payload=StringFormat(
      "{\"event\":\"%s\",\"symbol\":\"%s\",\"timeframe\":\"%s\",\"sleeve\":\"%s\",\"direction\":\"%s\",\"ea_version\":\"v5.1.0\","
      "\"phase\":\"V5_DEMO\",\"strategy_variant\":\"portfolio_trend_v510\",\"execution_mode\":\"DEMO\","
      "\"magic_number\":%I64u,\"boot_id\":\"%s\",\"signal_eval_id\":\"%s\","
      "\"ticket\":%I64u,\"order_ticket\":%I64u,\"deal_ticket\":%I64u,\"position_id\":%I64u,"
      "\"open_time\":%s,\"open_price\":%.8f,\"close_price\":%s,\"lots\":%.8f,\"sl\":0,\"tp\":0,\"pnl\":%s}",
      eventType,s.symbol,JsonEscape(StringSubstr(EnumToString(s.tf),7)),JsonEscape(s.sleeve),direction,s.magic,JsonEscape(bootId),JsonEscape(signalId),
      eventType=="trade_open"?orderTicket:dealTicket,orderTicket,dealTicket,positionId,
      openTime>0?"\""+IsoTime(openTime)+"\"":"null",openPrice,
      closePrice>0?DoubleToString(closePrice,8):"null",lots,
      eventType=="trade_close"?DoubleToString(pnl,2):"null");
   return SendWebhook(payload);
}

void SendSignalTelemetry(const V5Slot &s,const datetime barTime,const int current,const int target,
   const double close,const double channelHigh,const double channelLow,const double sma,
   const string signalId,const string orderStatus,const uint orderRetcode,const string orderMessage)
{
   if(!telemetryLeader)return;
   string direction=target==1?"BUY":target==-1?"SELL":"NONE";
   string decision=target!=current && target!=0?"ENTRY_READY":"NO_SIGNAL";
   string action=target!=current?(target==1?"ENTRY_READY_BUY":target==-1?"ENTRY_READY_SELL":"EXIT_TO_FLAT"):
      (target==1?"HOLD_LONG":target==-1?"HOLD_SHORT":"FLAT");
   string blockJson=StringFind(orderStatus,"FAIL")>=0?"\""+JsonEscape(orderMessage)+"\"":"null";
   string payload=StringFormat(
      "{\"event\":\"signal_eval\",\"symbol\":\"%s\",\"timeframe\":\"%s\",\"sleeve\":\"%s\",\"ea_version\":\"v5.1.0\",\"phase\":\"V5_DEMO\","
      "\"strategy_variant\":\"portfolio_trend_v510\",\"execution_mode\":\"DEMO\",\"order_send_allowed\":true,"
      "\"capital_enabled\":false,\"would_have_traded\":%s,\"signal_eval_id\":\"%s\",\"decision\":\"%s\","
      "\"technical_signal_status\":\"%s\",\"action\":\"%s\",\"direction\":\"%s\",\"h4_signal\":%d,"
      "\"bar_time\":\"%s\",\"eval_time\":\"%s\",\"magic_number\":%I64u,\"boot_id\":\"%s\","
      "\"close\":%.8f,\"channel_high\":%.8f,\"channel_low\":%.8f,\"sma\":%.8f,"
      "\"current_position\":%d,\"target_position\":%d,\"order_status\":\"%s\",\"order_retcode\":%u,"
      "\"order_message\":\"%s\",\"block_reason\":%s}",
      s.symbol,JsonEscape(StringSubstr(EnumToString(s.tf),7)),JsonEscape(s.sleeve),target!=current?"true":"false",JsonEscape(signalId),decision,
      target!=current?"ENTRY_READY":"NO_SIGNAL",action,direction,target,IsoTime(barTime),IsoTime(TimeCurrent()),
      s.magic,JsonEscape(bootId),close,channelHigh,channelLow,sma,current,target,JsonEscape(orderStatus),orderRetcode,
      JsonEscape(orderMessage),blockJson);
   bool ok=SendWebhook(payload);
   PrintFormat("[V5_TELEMETRY_%s] signal=%s | symbol=%s",ok?"OK":"SKIP_OR_FAIL",signalId,s.symbol);
}

bool DemoContext()
{
   return (bool)MQLInfoInteger(MQL_TESTER) ||
      ((bool)TerminalInfoInteger(TERMINAL_CONNECTED) &&
       (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO);
}

ulong Identity(const string symbol,const ENUM_TIMEFRAMES tf)
{
   string value=symbol+"_"+IntegerToString((int)tf);
   uint hash=2166136261;
   for(int i=0;i<StringLen(value);i++) hash=(hash^(uint)StringGetCharacter(value,i))*16777619;
   return InpMagicBase+(ulong)(hash%100000000);
}

void Record(const string event,const V5Slot &s,const string detail)
{
   PrintFormat("[V5_%s] version=v5.1.0 | symbol=%s | timeframe=%s | sleeve=%s | magic=%I64u | %s",
      event,s.symbol,EnumToString(s.tf),s.sleeve,s.magic,detail);
   if(audit!=INVALID_HANDLE)
   {
      FileWrite(audit,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),event,s.symbol,
         EnumToString(s.tf),s.magic,detail);
      FileFlush(audit);
   }
}

bool AddSlot(const string symbol,const ENUM_TIMEFRAMES tf,const int entryLookback,
   const int exitLookback,const int trendLookback,const string sleeve)
{
   ulong magic=Identity(symbol,tf);
   for(int i=0;i<ArraySize(slots);i++)
   {
      if(slots[i].symbol==symbol && slots[i].tf==tf) return true;
      if(slots[i].magic==magic) return false;
   }
   int n=ArraySize(slots);ArrayResize(slots,n+1);
   slots[n].symbol=symbol;slots[n].tf=tf;slots[n].entryLookback=entryLookback;
   slots[n].exitLookback=exitLookback;slots[n].trendLookback=trendLookback;
   slots[n].sleeve=sleeve;slots[n].magic=magic;slots[n].lastbar=0;
   SymbolSelect(symbol,true);
   return true;
}

int PositionState(const V5Slot &s,bool &foreign_netting)
{
   int result=0;foreign_netting=false;
   bool hedging=(ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      if(PositionGetTicket(i)==0 || PositionGetString(POSITION_SYMBOL)!=s.symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=s.magic)
      {if(!hedging) foreign_netting=true;continue;}
      int side=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?1:-1;
      if(result!=0 && result!=side) return 2;
      result=side;
   }
   return result;
}

bool CompletedTrade(const bool ok)
{
   uint code=trade.ResultRetcode();
   return ok && (code==TRADE_RETCODE_DONE || code==TRADE_RETCODE_DONE_PARTIAL);
}

bool HasPendingOrder(const V5Slot &s)
{
   for(int i=OrdersTotal()-1;i>=0;i--)
      if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==s.symbol &&
         (ulong)OrderGetInteger(ORDER_MAGIC)==s.magic) return true;
   return false;
}

bool ExecuteTarget(const V5Slot &s,const int target,const string signalId,
   string &orderStatus,uint &orderRetcode,string &orderMessage)
{
   orderStatus="NO_ACTION";orderRetcode=0;orderMessage="";
   if(!DemoContext()) {orderStatus="DEMO_REQUIRED";orderMessage="execution denied outside demo/tester";Record(orderStatus,s,orderMessage);return false;}
   if(!InpEnableDemoOrders) {orderStatus="OBSERVE";orderMessage="orders disabled by input";Record(orderStatus,s,orderMessage);return true;}
   if(HasPendingOrder(s)) {orderStatus="PENDING";orderMessage="wait for existing order";Record(orderStatus,s,orderMessage);return false;}
   trade.SetExpertMagicNumber(s.magic);trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFillingBySymbol(s.symbol);trade.SetAsyncMode(false);
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=s.symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=s.magic) continue;
      int side=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?1:-1;
      if(side==target) continue;
      double openPrice=PositionGetDouble(POSITION_PRICE_OPEN);
      double volume=PositionGetDouble(POSITION_VOLUME);
      datetime openTime=(datetime)PositionGetInteger(POSITION_TIME);
      bool closed=CompletedTrade(trade.PositionClose(ticket));
      orderRetcode=trade.ResultRetcode();orderMessage=trade.ResultRetcodeDescription();
      orderStatus=closed?"CLOSE_OK":"CLOSE_FAIL";
      Record(orderStatus,s,orderMessage);
      if(closed)
      {
         ulong dealTicket=trade.ResultDeal();
         double pnl=0;
         if(dealTicket>0 && HistoryDealSelect(dealTicket))
            pnl=HistoryDealGetDouble(dealTicket,DEAL_PROFIT)+HistoryDealGetDouble(dealTicket,DEAL_COMMISSION)+HistoryDealGetDouble(dealTicket,DEAL_SWAP);
         SendTradeTelemetry("trade_close",s,side==1?"BUY":"SELL",trade.ResultOrder(),dealTicket,ticket,signalId,
            openPrice,trade.ResultPrice(),volume,pnl,openTime);
      }
      if(!closed) return false;
   }
   bool foreign=false;int actual=PositionState(s,foreign);
   if(foreign || actual==2) return false;
   if(actual==target) return true;
   if(actual!=0) return false; // Partial close must finish before reversing.
   if(target==0) return true;
   double minvol=SymbolInfoDouble(s.symbol,SYMBOL_VOLUME_MIN);
   double maxvol=SymbolInfoDouble(s.symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(s.symbol,SYMBOL_VOLUME_STEP);
   if(step<=0 || minvol<=0 || maxvol<minvol) return false;
   double lots=NormalizeDouble(MathMax(minvol,MathMin(maxvol,MathFloor(InpLots/step+1e-9)*step)),8);
   bool sent=target==1?trade.Buy(lots,s.symbol,0,0,0,"v5 demo trend"):trade.Sell(lots,s.symbol,0,0,0,"v5 demo trend");
   bool filled=CompletedTrade(sent);
   orderRetcode=trade.ResultRetcode();orderMessage=trade.ResultRetcodeDescription();orderStatus=filled?"OPEN_OK":"OPEN_FAIL";
   Record(orderStatus,s,StringFormat("side=%s | lots=%.8f | retcode=%u | %s",
      target==1?"BUY":"SELL",lots,orderRetcode,orderMessage));
   if(filled)
   {
      ulong dealTicket=trade.ResultDeal();
      ulong positionId=0;
      if(dealTicket>0 && HistoryDealSelect(dealTicket))positionId=(ulong)HistoryDealGetInteger(dealTicket,DEAL_POSITION_ID);
      SendTradeTelemetry("trade_open",s,target==1?"BUY":"SELL",trade.ResultOrder(),dealTicket,positionId,signalId,
         trade.ResultPrice(),0,lots,0,TimeCurrent());
   }
   return filled;
}

void EvaluateSlot(V5Slot &s)
{
   datetime bar=iTime(s.symbol,s.tf,0);
   if(bar==0 || bar==s.lastbar) return;
   if(!(bool)SeriesInfoInteger(s.symbol,s.tf,SERIES_SYNCHRONIZED)) return;
   int needed=(int)MathMax(s.trendLookback,MathMax(s.entryLookback+1,s.exitLookback+1));
   MqlRates rates[];ArraySetAsSeries(rates,true);
   if(CopyRates(s.symbol,s.tf,1,needed,rates)!=needed) return;
   double hi=-DBL_MAX,lo=DBL_MAX,eh=-DBL_MAX,el=DBL_MAX,ma=0;
   for(int i=1;i<=s.entryLookback;i++){hi=MathMax(hi,rates[i].high);lo=MathMin(lo,rates[i].low);}
   for(int i=1;i<=s.exitLookback;i++){eh=MathMax(eh,rates[i].high);el=MathMin(el,rates[i].low);}
   for(int i=0;i<s.trendLookback;i++) ma+=rates[i].close;
   ma/=s.trendLookback;
   bool foreign=false;int current=PositionState(s,foreign);
   if(current==2 || foreign){Record("POSITION_CONFLICT",s,"positions require reconciliation");s.lastbar=bar;return;}
   int target=V5NextTarget(current,rates[0].close,hi,lo,eh,el,ma);
   string signalId=StringFormat("v5-sig-%I64u-%I64d",s.magic,(long)rates[0].time);
   string orderStatus=target==current?(target==0?"FLAT":"HOLD"):"NOT_SENT";
   uint orderRetcode=0;string orderMessage="";
   Record("ANALYSIS",s,StringFormat("bar=%s | close=%.8f | channel_high=%.8f | channel_low=%.8f | sma=%.8f | current=%d | target=%d",
      TimeToString(rates[0].time),rates[0].close,hi,lo,ma,current,target));
   // Terminal-wide claim prevents repeated entry after restart or duplicate attachment.
   string key=StringFormat("V5_%I64d_%I64u",AccountInfoInteger(ACCOUNT_LOGIN),s.magic);
   bool tester=(bool)MQLInfoInteger(MQL_TESTER);
   if(!tester)
   {
      if(!GlobalVariableCheck(key)) GlobalVariableSet(key,0);
      double previous=GlobalVariableGet(key);
      if(previous>=(double)bar)
      {
         SendSignalTelemetry(s,rates[0].time,current,target,rates[0].close,hi,lo,ma,signalId,"ALREADY_EVALUATED",0,"terminal claim exists");
         s.lastbar=bar;return;
      }
      if(!GlobalVariableSetOnCondition(key,(double)bar,previous))
      {
         SendSignalTelemetry(s,rates[0].time,current,target,rates[0].close,hi,lo,ma,signalId,"CLAIM_CONFLICT",0,"another attachment claimed this bar");
         return;
      }
   }
   if(target!=current) ExecuteTarget(s,target,signalId,orderStatus,orderRetcode,orderMessage);
   SendSignalTelemetry(s,rates[0].time,current,target,rates[0].close,hi,lo,ma,signalId,orderStatus,orderRetcode,orderMessage);
   // At most one attempt per bar. Failed/uncertain submissions are logged, never blindly retried.
   s.lastbar=bar;
}

void Scan()
{
   bool tester=(bool)MQLInfoInteger(MQL_TESTER);
   if(!tester && (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO)return;
   datetime now=TimeLocal();
   bool canSendTelemetry=EnsureTelemetryLeader();
   if(canSendTelemetry && !startupTelemetrySent)
   {
      startupTelemetrySent=true;lastHeartbeat=now;SendRuntimeTelemetry("startup");
   }
   else if(canSendTelemetry && !(bool)MQLInfoInteger(MQL_TESTER) && now-lastHeartbeat>=InpHeartbeatSeconds)
   {
      lastHeartbeat=now;SendRuntimeTelemetry("heartbeat");
   }
   if(!DemoContext())return; // Runtime health still reports while the broker reconnects.
   for(int i=0;i<ArraySize(slots);i++) EvaluateSlot(slots[i]);
}

int OnInit()
{
   if(InpEntryLookback<2 || InpExitLookback<1 || InpTrendLookback<2 ||
      InpEntryLookback2<2 || InpExitLookback2<1 || InpTrendLookback2<2 ||
      InpLots<=0 || InpPollSeconds<1 || InpHeartbeatSeconds<60)return INIT_PARAMETERS_INCORRECT;
   if(TerminalInfoInteger(TERMINAL_CONNECTED) && !DemoContext())return INIT_FAILED;
   string names[];int count=StringSplit(InpSymbols,',',names);
   for(int i=0;i<count;i++)
   {
      StringTrimLeft(names[i]);StringTrimRight(names[i]);if(StringLen(names[i])==0)continue;
      if(!AddSlot(names[i],InpTimeframe1,InpEntryLookback,InpExitLookback,InpTrendLookback,"CORE_D1"))return INIT_FAILED;
   }
   if(InpUseSecondTimeframe)
   {
      string experimental[];int experimentalCount=StringSplit(InpSecondSymbols,',',experimental);
      for(int i=0;i<experimentalCount;i++)
      {
         StringTrimLeft(experimental[i]);StringTrimRight(experimental[i]);if(StringLen(experimental[i])==0)continue;
         if(!AddSlot(experimental[i],InpTimeframe2,InpEntryLookback2,InpExitLookback2,InpTrendLookback2,"EXPERIMENTAL_H4"))return INIT_FAILED;
      }
   }
   if(ArraySize(slots)==0)return INIT_PARAMETERS_INCORRECT;
   bootId=StringFormat("v5-%I64d-%I64d",(long)TimeLocal(),ChartID());
   string filename=StringFormat("V5_demo_%I64d_%I64d.csv",ChartID(),(long)TimeLocal());
   audit=FileOpen(filename,FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');
   if(audit==INVALID_HANDLE)return INIT_FAILED;
   FileWrite(audit,"broker_time","event","symbol","timeframe","magic","detail");
   if(!MQLInfoInteger(MQL_TESTER) && !EventSetTimer(InpPollSeconds))return INIT_FAILED;
   PrintFormat("[V5_INIT] version=v5.1.0 | slots=%d | demo_orders=%s | demo/tester only | no real-capital authorization",ArraySize(slots),InpEnableDemoOrders?"true":"false");
   return INIT_SUCCEEDED;
}
void OnTick(){Scan();}
void OnTimer(){Scan();}
void OnDeinit(const int reason)
{
   if(startupTelemetrySent)SendRuntimeTelemetry("deinit",reason);
   if(telemetryLeader && telemetryLeaderKey!="")GlobalVariableSet(telemetryLeaderKey,0);
   telemetryLeader=false;
   EventKillTimer();if(audit!=INVALID_HANDLE)FileClose(audit);
   PrintFormat("[V5_DEINIT] reason=%d | positions retained for restart",reason);
}
