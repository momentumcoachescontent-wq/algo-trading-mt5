type Row = Record<string, unknown>
const obj = (v: unknown): Row | null => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Row : null
const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : null
const text = (v: unknown) => typeof v === 'string' ? v.slice(0, 180) : null
const brokerTime = (v: unknown) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(v) ? v : null
const symbols = new Set(['USDJPY', 'USDCHF', 'XAUUSD', 'AMD'])

export function publicTrendCharts(value: unknown) {
  const source = obj(value)
  if (!source || source.schema_version !== 1) return null
  const cutoff = brokerTime(source.as_of_broker)
  return {
    schema_version: 1, status: text(source.status), observed_at: text(source.observed_at), release_id: text(source.release_id),
    as_of_broker: cutoff, time_basis: 'BROKER_WALL_CLOCK_NO_UTC_CONVERSION', execution_authority: 'NONE',
    series: (Array.isArray(source.series) ? source.series : []).slice(0, 8).flatMap(value => {
      const s = obj(value)
      if (!s || !symbols.has(String(s.symbol)) || !['D1', 'H4'].includes(String(s.timeframe))) return []
      let prior = ''
      const bars = (Array.isArray(s.bars) ? s.bars : []).slice(-160).flatMap(value => {
        if (!Array.isArray(value) || value.length !== 13) return []
        const time = brokerTime(value[0])
        const prices = value.slice(1, 5).map(num)
        if (!time || !cutoff || time > cutoff || time <= prior || prices.some(p => p == null || p <= 0)) return []
        const [open, high, low, close] = prices as number[]
        if (low > Math.min(open, close) || high < Math.max(open, close) || high < low) return []
        prior = time
        const indicators = value.slice(5, 11).map(num)
        const [ma, hi, lo] = indicators
        const closed = value[12] === 1
        const signal = closed && ma !== null && hi !== null && lo !== null ? (close > hi && close > ma ? 1 : close < lo && close < ma ? -1 : 0) : 0
        return [[time, ...prices, ...indicators, signal, closed ? 1 : 0]]
      })
      const ea = obj(s.ea_decision)
      return [{
        symbol: String(s.symbol), timeframe: String(s.timeframe), status: text(s.status), execution_sleeve: s.execution_sleeve === true, ea_alignment: text(s.ea_alignment),
        entry_lookback: num(s.entry_lookback), exit_lookback: num(s.exit_lookback), sma_period: num(s.sma_period), atr_period: num(s.atr_period),
        source_file: text(s.source_file), source_sha256: text(s.source_sha256), source_modified_at: text(s.source_modified_at),
        source_rows: num(s.source_rows), last_closed_bar: brokerTime(s.last_closed_bar), bars,
        ea_decision: ea ? { bar_time: brokerTime(ea.bar_time), close: num(ea.close), sma: num(ea.sma),
          channel_high: num(ea.channel_high), channel_low: num(ea.channel_low), current_position: num(ea.current_position),
          target_position: num(ea.target_position), order_status: text(ea.order_status), order_message: text(ea.order_message),
          health: text(ea.health), evaluated_at: text(ea.evaluated_at) } : null,
      }]
    }),
  }
}
