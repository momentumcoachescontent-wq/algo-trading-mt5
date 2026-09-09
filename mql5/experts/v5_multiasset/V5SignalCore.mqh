#ifndef V5_SIGNAL_CORE_MQH
#define V5_SIGNAL_CORE_MQH
// Closed candle compared with channels that exclude that candle.
int V5NextTarget(const int current,const double close_price,
                 const double entry_high,const double entry_low,
                 const double exit_high,const double exit_low,const double trend)
{
   if(close_price>entry_high && close_price>trend) return 1;
   if(close_price<entry_low && close_price<trend) return -1;
   if(current==1 && close_price<exit_low) return 0;
   if(current==-1 && close_price>exit_high) return 0;
   return current;
}
#endif
