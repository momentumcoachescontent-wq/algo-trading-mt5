type Row = Record<string, unknown>
const object = (v: unknown): Row | null => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Row : null
const count = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 ? v : null
const instant = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)) ? v : null
const release = (v: unknown) => typeof v === 'string' && /^v\d[\w.-]{0,100}$/.test(v) ? v : null

/** Public allowlist: no raw decisions, account scope, P&L or execution instructions. */
export function publicResearchEvidence(input: unknown, nowMs: number) {
  const row = object(input)
  if (!row || row.schema_version !== 1) return null
  const generated = instant(row.generated_at_utc)
  const asOf = instant(row.as_of_utc)
  const ageSeconds = generated ? Math.round((nowMs - Date.parse(generated)) / 1000) : null
  const validClock = asOf && generated && Date.parse(asOf) <= Date.parse(generated) + 120000 && Date.parse(asOf) <= nowMs + 120000 && ageSeconds != null && ageSeconds >= -120
  const freshness = !validClock ? 'UNVERIFIED' : ageSeconds > 86400 ? 'STALE_RESEARCH' : 'AT_RECORDED_CUTOFF'
  const allowed = ['INSUFFICIENT_EXECUTION_SAMPLE', 'DESCRIPTIVE_DATASET', 'DATASET_READY', 'READY_FOR_REVIEW', 'UNAVAILABLE']
  const coverage = object(row.feature_coverage)
  const features: Record<string, {known: number | null; total: number | null}> = {}
  for (const name of ['atr', 'spread_atr_ratio', 'entry_distance_atr', 'htf_context']) {
    const value = object(coverage?.[name])
    const known = count(value?.known), total = count(value?.total)
    features[name] = { known: known != null && total != null && known <= total ? known : null, total }
  }
  return {
    schema_version: 1,
    status: allowed.includes(String(row.status)) ? String(row.status) : 'REVIEW_REQUIRED',
    freshness, as_of_utc: asOf, generated_at_utc: generated, age_seconds: ageSeconds,
    stale_after_seconds: 86400,
    decision_count: count(row.decision_count), entry_candidate_count: count(row.entry_candidate_count),
    linked_closed_trades: count(row.linked_closed_trades), unlinked_execution_events: count(row.unlinked_execution_events),
    mature_hypothetical_outcomes: count(row.mature_hypothetical_outcomes), feature_coverage: features,
    active_release_id: release(row.active_release_id), source_candidate: release(row.source_candidate),
    source_candidate_active: row.source_candidate_active === true,
    execution_authority: 'NONE', refresh_mode: 'ON_DEMAND_DATASET',
    profitability_validated: false,
  }
}
