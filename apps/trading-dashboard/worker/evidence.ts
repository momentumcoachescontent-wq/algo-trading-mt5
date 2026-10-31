type Row = Record<string, unknown>

export function analysisIssue(raw: Row | null): string | null {
  if (!raw) return 'MISSING_ANALYSIS'
  // Both fields are broker wall-clock. Never compare a broker timestamp to browser UTC.
  const bar = Date.parse(String(raw.bar_time ?? ''))
  const evaluated = Date.parse(String(raw.eval_time ?? ''))
  if (!Number.isFinite(bar) || !Number.isFinite(evaluated)) return 'MISSING_BAR_TIME'
  if (bar > evaluated) return 'FUTURE_BAR'
  return evaluated - bar > 7 * 86400000 ? 'HISTORICAL_BAR' : null
}

export function preferEvidence(a: Row, b: Row): Row {
  const rank = (e: Row) => {
    const s = String(e.order_status ?? '')
    return s.endsWith('_OK') ? 4 : /^(RISK_|OPEN_|CLOSE_)/.test(s) ? 3 : s === 'ALREADY_EVALUATED' ? 0 : 1
  }
  return rank(b) > rank(a) ? b : a
}
