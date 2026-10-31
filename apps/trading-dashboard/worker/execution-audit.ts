type Row = Record<string, unknown>
const record = (value: unknown): Row | null => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Row : null
const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null
const text = (value: unknown) => typeof value === 'string' ? value.slice(0, 180) : null

export function publicExecutionAudit(value: unknown) {
  const source = record(value)
  if (!source || source.schema_version !== 1) return null
  return {
    schema_version: 1, observed_at: text(source.observed_at),
    requests_24h: number(source.requests_24h), confirmed_deals_24h: number(source.confirmed_deals_24h), rejected_24h: number(source.rejected_24h),
    rows: (Array.isArray(source.rows) ? source.rows : []).slice(0, 25).flatMap(value => {
      const row = record(value)
      if (!row) return []
      const confirmed = row.fill_confirmed === true && typeof row.broker_deal_ticket === 'string' && row.broker_deal_ticket.length > 0
      return [{ request_id: text(row.request_id), observed_at: text(row.observed_at), symbol: text(row.symbol), timeframe: text(row.timeframe),
        action: text(row.action), status: text(row.status), requested_lots: number(row.requested_lots), requested_sl: number(row.requested_sl), requested_tp: number(row.requested_tp),
        broker_retcode: number(row.broker_retcode), broker_order_ticket: text(row.broker_order_ticket), broker_deal_ticket: confirmed ? text(row.broker_deal_ticket) : null,
        fill_price: confirmed ? number(row.fill_price) : null, fill_confirmed: confirmed }]
    }),
  }
}
