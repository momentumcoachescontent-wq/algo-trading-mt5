import { buildPortfolioRisk } from './portfolio-risk.ts'
import { analysisIssue, preferEvidence } from './evidence.ts'
import { publicResearchEvidence } from './research-evidence.ts'
type Env = {
  ASSETS: {
    fetch(request: Request): Promise<Response>
  }
  SUPABASE_URL: string
  SUPABASE_SERVICE_ROLE_KEY?: string
  SUPABASE_ANON_KEY?: string
}

const BUG_DATA_01_CUTOFF = '2026-05-10T15:55:00.000Z'
const ACTIVE_EA_VERSION = 'v4.44.1'
const ACTIVE_STRATEGY_VARIANT = 'stage10_usdjpy_buy_v4401_demo'
const STAGE10_VERSIONS = [ACTIVE_EA_VERSION, 'v4.44.0', 'v4.43.0', 'v4.43.1'] as const
const V5_EA_VERSION = 'v5.2.0'
const V5_STRATEGY_VARIANT = 'portfolio_trend_v520'
const V5_SYMBOLS = ['USDJPY', 'USDCHF', 'XAUUSD', 'AMD'] as const
const V5_SLEEVES = [
  { symbol: 'USDJPY', timeframe: 'D1', sleeve: 'CORE_D1', experimental: false },
  { symbol: 'USDCHF', timeframe: 'D1', sleeve: 'CORE_D1', experimental: false },
  { symbol: 'XAUUSD', timeframe: 'D1', sleeve: 'CORE_D1', experimental: false },
  { symbol: 'XAUUSD', timeframe: 'H4', sleeve: 'EXPERIMENTAL_H4', experimental: true },
  { symbol: 'AMD', timeframe: 'H4', sleeve: 'EXPERIMENTAL_H4', experimental: true },
] as const
const V5_GATE_TRADES = 60

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  })
}

function getSupabaseKey(env: Env): string | null {
  return env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY || null
}

function supabaseHeaders(key: string): HeadersInit {
  return {
    apikey: key,
    authorization: `Bearer ${key}`,
    'accept-profile': 'public',
    'content-profile': 'public',
  }
}

async function portfolioRiskHistory(env:Env, runtime:Record<string, unknown>):Promise<Array<Record<string, unknown>>|null> {
  if(!env.SUPABASE_SERVICE_ROLE_KEY || !runtime.account_login || !runtime.account_server)return null
  try {
    const response=await fetch(`${env.SUPABASE_URL}/rest/v1/rpc/portfolio_risk_history`,{
      method:'POST',headers:{...supabaseHeaders(env.SUPABASE_SERVICE_ROLE_KEY),'content-type':'application/json'},
      body:JSON.stringify({p_account:String(runtime.account_login),p_server:runtime.account_server}),signal:AbortSignal.timeout(4000)})
    if(!response.ok)return null
    const rows=await response.json()
    return Array.isArray(rows)?rows:null
  } catch {return null}
}

async function supabaseGet(env: Env, path: string): Promise<Response> {
  const key = getSupabaseKey(env)

  if (!env.SUPABASE_URL) {
    return json({ ok: false, error: 'SUPABASE_URL missing' }, 500)
  }

  if (!key) {
    return json({ ok: false, error: 'No Supabase key configured' }, 500)
  }

  const url = `${env.SUPABASE_URL}/rest/v1/${path}`

  const res = await fetch(url, {
    method: 'GET',
    headers: supabaseHeaders(key),
  })

  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    return json(
      {
        ok: false,
        status: res.status,
        error: 'Supabase request failed',
        detail,
        path,
      },
      500,
    )
  }

  const rows = await res.json()
  return json({ ok: true, rows })
}

async function supabaseRows(
  env: Env,
  path: string,
  signal: AbortSignal = AbortSignal.timeout(8000),
): Promise<{ ok: true; rows: Array<Record<string, unknown>> } | { ok: false; response: Response; upstreamStatus?: number }> {
  const key = getSupabaseKey(env)

  if (!env.SUPABASE_URL) {
    return { ok: false, response: json({ ok: false, error: 'SUPABASE_URL missing' }, 500) }
  }

  if (!key) {
    return { ok: false, response: json({ ok: false, error: 'No Supabase key configured' }, 500) }
  }

  let response: Response
  try {
    response = await fetch(`${env.SUPABASE_URL}/rest/v1/${path}`, {
      method: 'GET',
      headers: supabaseHeaders(key),
      signal,
    })
  } catch {
    return { ok: false, response: json({ ok: false, error: 'La fuente de datos no respondió a tiempo. Reintentando; no se muestran cifras nuevas.', code: 'UPSTREAM_UNAVAILABLE' }, 503) }
  }

  if (!response.ok) {
    return {
      ok: false,
      response: json({
        ok: false,
        status: response.status,
        error: 'Supabase request failed',
      }, 500),
      upstreamStatus: response.status,
    }
  }

  try {
    const rows: unknown = await response.json()
    if (!Array.isArray(rows)) throw new Error('Invalid upstream shape')
    return { ok: true, rows: rows as Array<Record<string, unknown>> }
  } catch {
    return { ok: false, response: json({ ok: false, error: 'Invalid upstream data', code: 'UPSTREAM_INVALID_BODY' }, 502) }
  }
}

async function v5SnapshotRows(env: Env) {
  // Share the deadline across RPC and its optional public-REST fallback.
  // A restricted existing key never gains access to the private evidence schema.
  const signal = AbortSignal.timeout(8000)
  const rpc = await supabaseRows(env, 'rpc/dashboard_v5_snapshot', signal)
  if (rpc.ok || env.SUPABASE_SERVICE_ROLE_KEY || !env.SUPABASE_ANON_KEY ||
      ![401, 403, 404].includes(rpc.upstreamStatus ?? 0)) return rpc

  const result = await Promise.all([
    supabaseRows(env, `ea_events?select=created_at,event,symbol,ea_version,account_login,account_environment,balance,raw_payload&symbol=eq.USDJPY&ea_version=eq.${V5_EA_VERSION}&order=created_at.desc&limit=1`, signal),
    supabaseRows(env, `signal_evals?select=symbol,created_at,eval_time,bar_h4,raw_payload&ea_version=eq.${V5_EA_VERSION}&order=created_at.desc&limit=1000`, signal),
    supabaseRows(env, `trades?select=symbol,created_at,close_time,event_type,direction,pnl,position_id,open_time,open_price,lots,raw_payload&ea_version=eq.${V5_EA_VERSION}&order=created_at.desc&limit=1000`, signal),
  ])
  const [lifecycle, signals, trades] = result
  if (!lifecycle.ok) return lifecycle
  if (!signals.ok) return signals
  if (!trades.ok) return trades
  return { ok: true as const, rows: [{ lifecycle: lifecycle.rows, signals: signals.rows, trades: trades.rows }] }
}

function textValue(value: unknown): string {
  return value == null ? '' : String(value)
}

function isEntryReady(row: Record<string, unknown>): boolean {
  const decision = textValue(row.decision).toUpperCase()
  const action = textValue(row.action).toUpperCase()
  return decision.includes('ENTRY_READY') || action.startsWith('ENTRY_READY') || action === 'ENTRY_ACCEPTED'
}

type SignalOutcome = 'ENTRY_READY' | 'BLOCKED' | 'ERROR' | 'OTHER'

function classifySignal(row: Record<string, unknown>): SignalOutcome {
  const decision = textValue(row.decision).toUpperCase()
  const action = textValue(row.action).toUpperCase()

  if (isEntryReady(row)) return 'ENTRY_READY'
  if (decision.includes('ERROR') || action.includes('ERROR')) return 'ERROR'
  if (decision.includes('BLOCKED') || action.includes('BLOCKED') || row.block_reason != null) {
    return 'BLOCKED'
  }
  return 'OTHER'
}

function parseRawPayload(value: unknown): Record<string, unknown> | null {
  if (value != null && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  if (typeof value !== 'string') return null

  try {
    const parsed = JSON.parse(value)
    return parsed != null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null
  } catch {
    return null
  }
}

function normalizedSpreadAtr(row: Record<string, unknown>): number | null {
  if (row.spread_atr_ratio != null) {
    const direct = Number(row.spread_atr_ratio)
    if (Number.isFinite(direct)) return direct
  }

  const fallback = Number(parseRawPayload(row.raw_payload)?.spread_atr_ratio)
  return Number.isFinite(fallback) ? fallback : null
}

function normalizeSignal(row: Record<string, unknown>): Record<string, unknown> {
  return { ...row, spread_atr_ratio: normalizedSpreadAtr(row) }
}

function booleanValue(value: unknown): boolean | null {
  return value === true || value === false ? value : null
}

function normalizeLifecycle(row: Record<string, unknown>): Record<string, unknown> {
  const executionScope = parseRawPayload(row.execution_scope)

  return {
    ...row,
    execution_scope: executionScope,
    observed_state: row.event === 'ea_deinit' ? 'STOPPED' : 'LAST_INIT_ONLY',
    capital_enabled: booleanValue(executionScope?.capital_enabled),
    order_send_allowed: booleanValue(executionScope?.order_send_allowed),
  }
}

function signalBarKey(row: Record<string, unknown>): string {
  return [row.symbol, row.bar_h4 || row.eval_time, row.ea_version, row.strategy_variant]
    .map(textValue)
    .join('|')
}

function uniqueSignals(rows: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  const seen = new Set<string>()
  return rows.filter((row) => {
    const key = signalBarKey(row)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function strategySummary(
  version: string,
  signals: Array<Record<string, unknown>>,
  trades: Array<Record<string, unknown>>,
) {
  const versionSignals = uniqueSignals(signals.filter((row) => row.ea_version === version))
  const versionTrades = trades.filter(
    (row) => row.ea_version === version && row.exclude_from_edge !== true,
  )
  const closedTrades = versionTrades.filter((row) => row.close_time != null || row.event_type === 'close')
  const pnl = closedTrades
    .map((row) => Number(row.pnl))
    .filter((value) => Number.isFinite(value))
  const grossProfit = pnl.filter((value) => value > 0).reduce((total, value) => total + value, 0)
  const grossLoss = Math.abs(pnl.filter((value) => value < 0).reduce((total, value) => total + value, 0))
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : null
  let equity = 0
  let peak = 0
  let maxDrawdownPnl = 0
  for (const value of [...pnl].reverse()) {
    equity += value
    peak = Math.max(peak, equity)
    maxDrawdownPnl = Math.max(maxDrawdownPnl, peak - equity)
  }

  return {
    ea_version: version,
    evaluations: versionSignals.length,
    entry_ready: versionSignals.filter((row) => classifySignal(row) === 'ENTRY_READY').length,
    blocked: versionSignals.filter((row) => classifySignal(row) === 'BLOCKED').length,
    errors: versionSignals.filter((row) => classifySignal(row) === 'ERROR').length,
    other: versionSignals.filter((row) => classifySignal(row) === 'OTHER').length,
    closed_trades: closedTrades.length,
    total_pnl: pnl.reduce((total, value) => total + value, 0),
    profit_factor: profitFactor,
    expectancy_pnl: pnl.length > 0 ? pnl.reduce((total, value) => total + value, 0) / pnl.length : null,
    win_rate: pnl.length > 0 ? pnl.filter((value) => value > 0).length / pnl.length : null,
    max_drawdown_pnl: maxDrawdownPnl,
    sample_basis: 'CLEAN_CLOSED_TRADES',
    economic_gate: closedTrades.length === 0 ? 'NO_ECONOMIC_SAMPLE' : 'INSUFFICIENT_SAMPLE',
  }
}

async function programStatus(env: Env): Promise<Response> {
  const versions = STAGE10_VERSIONS.join(',')
  const [lifecycle, signals, trades] = await Promise.all([
    supabaseRows(
      env,
      `ea_events?select=created_at,event,symbol,ea_version,phase,request_id,guard_version,execution_mode,execution_scope,boot_id,terminal_time,account_login,account_environment&symbol=eq.USDJPY&ea_version=in.(${versions})&order=created_at.desc&limit=200`,
    ),
    supabaseRows(
      env,
      `signal_evals?select=created_at,symbol,eval_time,bar_h4,ea_version,decision,action,block_reason,execution_mode,strategy_variant&symbol=eq.USDJPY&ea_version=in.(${versions})&order=created_at.desc&limit=1000`,
    ),
    supabaseRows(
      env,
      `trades?select=created_at,ea_version,event_type,close_time,pnl,execution_mode,strategy_variant,exclude_from_edge&symbol=eq.USDJPY&ea_version=in.(${versions})&order=created_at.desc&limit=1000`,
    ),
  ])

  if (!lifecycle.ok) return lifecycle.response
  if (!signals.ok) return signals.response
  if (!trades.ok) return trades.response

  const normalizedLifecycle = lifecycle.rows.map(normalizeLifecycle)
  const latestLifecycle = STAGE10_VERSIONS.map((version) =>
    normalizedLifecycle.find((row) => row.ea_version === version) ?? null,
  ).filter((row) => row != null)

  return json({
    ok: true,
    generated_at: new Date().toISOString(),
    active_ea_version: ACTIVE_EA_VERSION,
    read_scope: 'bounded samples; not a complete portfolio ledger',
    program_decision: {
      active_challenger: 'V5_PORTFOLIO_DEMO',
      stage10c_v443x: 'HALTED_NO_PROMOTION',
      worker_331: 'OBSERVABILITY_ONLY',
      stage10d: 'SUPERSEDED_BY_V5_SCREEN',
    },
    lifecycle: latestLifecycle,
    strategy: STAGE10_VERSIONS.map((version) => strategySummary(version, signals.rows, trades.rows)),
    challengers: [
      { id: 'portfolio_trend_v500', status: 'DEMO_ACTIVE_FIRST_SIGNAL_MARKET_CLOSED', economic_gate: 'V5C_60_TRADES_PF_GT_1_15_COST_STRESS_REQUIRED' },
      { id: 'sleeve_b_sell_touch025', status: 'PLANNED_NOT_AUTHORIZED', economic_gate: 'STAGE10A_GATE_REQUIRED' },
      { id: 'frequency_body015', status: 'PLANNED_NOT_AUTHORIZED', economic_gate: 'STRONG_GATE_NOT_APPROVED' },
      { id: 'stage10d_donchian', status: 'OFFLINE_RESEARCH', economic_gate: '80_TRADES_PF_GT_1_15_OOS_REQUIRED' },
    ],
  })
}

const tradeSelect = [
  'created_at',
  'symbol',
  'position_id',
  'ticket',
  'direction',
  'open_time',
  'open_price',
  'sl',
  'tp',
  'lots',
  'close_time',
  'close_price',
  'pnl',
  'close_reason',
  'ea_version',
  'event_type',
  'phase',
  'ledger_classification',
  'exclude_from_edge',
  'data_quality_notes',
].join(',')

const signalSelect = [
  'created_at',
  'symbol',
  'eval_time',
  'bar_h4',
  'decision',
  'action',
  'block_reason',
  'direction',
  'entry_price',
  'sl_price',
  'tp_price',
  'atr_h4',
  'distance_to_ema_atr',
  'trend_state',
  'volatility_state',
  'session',
  'bias_d1',
  'spread_atr_ratio',
  'raw_payload',
  'ea_version',
  'strategy_variant',
  'phase',
].join(',')

async function openPositions(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `trades?select=${tradeSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&close_time=is.null&exclude_from_edge=eq.false&order=open_time.desc&limit=50`,
  )
}

async function cleanEdgeTrades(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `trades?select=${tradeSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&exclude_from_edge=eq.false&order=created_at.desc&limit=50`,
  )
}

async function excludedTrades(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `trades?select=${tradeSelect}&exclude_from_edge=eq.true&order=created_at.desc&limit=50`,
  )
}

async function latestTrades(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `trades?select=${tradeSelect}&order=created_at.desc&limit=50`,
  )
}

async function latestSignals(env: Env): Promise<Response> {
  const result = await supabaseRows(
    env,
    `signal_evals?select=${signalSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&strategy_variant=eq.${ACTIVE_STRATEGY_VARIANT}&order=created_at.desc&limit=50`,
  )
  return result.ok ? json({ ok: true, rows: result.rows.map(normalizeSignal) }) : result.response
}

async function liveValidationSignals(env: Env): Promise<Response> {
  const result = await supabaseRows(
    env,
    `signal_evals?select=${signalSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&strategy_variant=eq.${ACTIVE_STRATEGY_VARIANT}&created_at=gte.${encodeURIComponent(BUG_DATA_01_CUTOFF)}&order=created_at.desc&limit=100`,
  )
  return result.ok ? json({ ok: true, rows: result.rows.map(normalizeSignal) }) : result.response
}

function isSignalIncomplete(row: Record<string, unknown>): boolean {
  const entryReady = isEntryReady(row)
  return (
    row.raw_payload == null ||
    (entryReady && row.direction == null) ||
    row.atr_h4 == null ||
    row.distance_to_ema_atr == null ||
    row.trend_state == null ||
    row.volatility_state == null ||
    row.session == null
  )
}

function isOpenTradeIncomplete(row: Record<string, unknown>): boolean {
  return (
    row.close_time == null &&
    (
      row.open_price == null ||
      row.sl == null ||
      row.tp == null ||
      row.lots == null
    )
  )
}

function isClosedTradeIncomplete(row: Record<string, unknown>): boolean {
  return (
    row.close_time != null &&
    (
      row.close_price == null ||
      row.pnl == null ||
      row.close_reason == null
    )
  )
}

async function dataQuality(env: Env): Promise<Response> {
  const key = getSupabaseKey(env)

  if (!env.SUPABASE_URL) {
    return json({ ok: false, error: 'SUPABASE_URL missing' }, 500)
  }

  if (!key) {
    return json({ ok: false, error: 'No Supabase key configured' }, 500)
  }

  const [signalsRes, tradesRes, latestSignalRes] = await Promise.all([
    fetch(
      `${env.SUPABASE_URL}/rest/v1/signal_evals?select=${signalSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&strategy_variant=eq.${ACTIVE_STRATEGY_VARIANT}&created_at=gte.${encodeURIComponent(
        BUG_DATA_01_CUTOFF,
      )}&order=created_at.desc&limit=200`,
      { headers: supabaseHeaders(key) },
    ),
    fetch(
      `${env.SUPABASE_URL}/rest/v1/trades?select=${tradeSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&exclude_from_edge=eq.false&created_at=gte.${encodeURIComponent(
        BUG_DATA_01_CUTOFF,
      )}&order=created_at.desc&limit=200`,
      { headers: supabaseHeaders(key) },
    ),
    fetch(
      `${env.SUPABASE_URL}/rest/v1/signal_evals?select=${signalSelect}&symbol=eq.USDJPY&ea_version=eq.${ACTIVE_EA_VERSION}&strategy_variant=eq.${ACTIVE_STRATEGY_VARIANT}&order=created_at.desc&limit=1`,
      { headers: supabaseHeaders(key) },
    ),
  ])

  if (!signalsRes.ok) {
    return json({
      ok: false,
      error: 'signal_evals quality query failed',
      status: signalsRes.status,
      detail: await signalsRes.text().catch(() => ''),
    }, 500)
  }

  if (!tradesRes.ok) {
    return json({
      ok: false,
      error: 'trades quality query failed',
      status: tradesRes.status,
      detail: await tradesRes.text().catch(() => ''),
    }, 500)
  }

  if (!latestSignalRes.ok) {
    return json({
      ok: false,
      error: 'latest signal query failed',
      status: latestSignalRes.status,
      detail: await latestSignalRes.text().catch(() => ''),
    }, 500)
  }

  const signals = await signalsRes.json() as Array<Record<string, unknown>>
  const trades = await tradesRes.json() as Array<Record<string, unknown>>
  const latestSignalRows = await latestSignalRes.json() as Array<Record<string, unknown>>
  const latestSignal = latestSignalRows[0] ? normalizeSignal(latestSignalRows[0]) : null
  const uniqueSignalRows = uniqueSignals(signals)

  const incompleteSignals = uniqueSignalRows.filter(isSignalIncomplete)
  const incompleteTradeOpens = trades.filter(isOpenTradeIncomplete)
  const incompleteTradeCloses = trades.filter(isClosedTradeIncomplete)

  return json({
    ok: true,
    cutoff: BUG_DATA_01_CUTOFF,
    scope: {
      symbol: 'USDJPY',
      ea_version: ACTIVE_EA_VERSION,
      strategy_variant: ACTIVE_STRATEGY_VARIANT,
    },
    summary: {
      sampled_signal_rows: signals.length,
      unique_h4_evaluations: uniqueSignalRows.length,
      duplicate_signal_rows: signals.length - uniqueSignalRows.length,
      live_signal_evals_checked: uniqueSignalRows.length,
      live_incomplete_signal_evals: incompleteSignals.length,
      live_trades_checked: trades.length,
      live_incomplete_trade_opens: incompleteTradeOpens.length,
      live_incomplete_trade_closes: incompleteTradeCloses.length,
      latest_signal_is_pre_bug_data_01: latestSignal
        ? String(latestSignal.created_at) < BUG_DATA_01_CUTOFF
        : true,
      latest_signal_raw_payload_ok: latestSignal ? latestSignal.raw_payload != null : false,
      latest_signal_context_ok: latestSignal ? !isSignalIncomplete(latestSignal) : false,
    },
    latest_signal: latestSignal,
    samples: {
      live_incomplete_signal_evals: incompleteSignals.slice(0, 10),
      live_incomplete_trade_opens: incompleteTradeOpens.slice(0, 10),
      live_incomplete_trade_closes: incompleteTradeCloses.slice(0, 10),
    },
  })
}

function finiteNumber(value: unknown): number | null {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function rowTime(row: Record<string, unknown>): number {
  const value = row.close_time ?? row.created_at ?? row.eval_time ?? row.terminal_time
  const parsed = Date.parse(String(value ?? ''))
  return Number.isFinite(parsed) ? parsed : 0
}

function performanceMetrics(rows: Array<Record<string, unknown>>) {
  const closed = rows
    .filter((row) => row.close_time != null || row.event_type === 'close')
    .map<Record<string, unknown> & { numeric_pnl: number | null }>((row) => ({ ...row, numeric_pnl: finiteNumber(row.pnl) }))
    .filter((row) => row.numeric_pnl != null)
    .sort((a, b) => rowTime(a) - rowTime(b))
  const pnl = closed.map((row) => row.numeric_pnl as number)
  const grossProfit = pnl.filter((value) => value > 0).reduce((sum, value) => sum + value, 0)
  const grossLoss = Math.abs(pnl.filter((value) => value < 0).reduce((sum, value) => sum + value, 0))
  let cumulative = 0
  let peak = 0
  let maxDrawdown = 0
  const equity_curve = closed.map((row) => {
    cumulative += row.numeric_pnl as number
    peak = Math.max(peak, cumulative)
    maxDrawdown = Math.max(maxDrawdown, peak - cumulative)
    return {
      at: row.close_time ?? row.created_at,
      pnl: row.numeric_pnl,
      cumulative_pnl: cumulative,
    }
  })

  return {
    closed_trades: closed.length,
    wins: pnl.filter((value) => value > 0).length,
    losses: pnl.filter((value) => value <= 0).length,
    realized_pnl: pnl.reduce((sum, value) => sum + value, 0),
    profit_factor: grossLoss > 0 ? grossProfit / grossLoss : null,
    expectancy: pnl.length > 0 ? pnl.reduce((sum, value) => sum + value, 0) / pnl.length : null,
    win_rate: pnl.length > 0 ? pnl.filter((value) => value > 0).length / pnl.length : null,
    max_drawdown: maxDrawdown,
    equity_curve,
  }
}

function clamp(value: number, minimum = 0, maximum = 100): number {
  return Math.min(maximum, Math.max(minimum, value))
}

function decisionEvaluation(row: Record<string, unknown> | null) {
  const raw = parseRawPayload(row?.raw_payload)
  const close = finiteNumber(raw?.close)
  const channelHigh = finiteNumber(raw?.channel_high)
  const channelLow = finiteNumber(raw?.channel_low)
  const exitChannelHigh = finiteNumber(raw?.exit_channel_high)
  const exitChannelLow = finiteNumber(raw?.exit_channel_low)
  const sma = finiteNumber(raw?.sma)
  const current = finiteNumber(raw?.current_position)
  const target = finiteNumber(raw?.target_position)
  const orderStatus = String(raw?.order_status ?? 'NO_DATA').toUpperCase()
  const orderMessage = String(raw?.order_message ?? '')
  const validInputs = close != null && channelHigh != null && channelLow != null && sma != null && channelHigh > channelLow
  const trend = validInputs ? (close > sma ? 'BULLISH' : close < sma ? 'BEARISH' : 'NEUTRAL') : 'NO_DATA'
  const potentialDirection = trend === 'BULLISH' ? 'BUY' : trend === 'BEARISH' ? 'SELL' : 'NONE'
  const triggerPrice = trend === 'BULLISH' ? channelHigh : trend === 'BEARISH' ? channelLow : null
  const distanceToTrigger = validInputs && triggerPrice != null && close > 0
    ? Math.max(0, trend === 'BULLISH' ? ((triggerPrice - close) / close) * 100 : ((close - triggerPrice) / close) * 100)
    : null
  const channelPosition = validInputs ? clamp(((close - channelLow) / (channelHigh - channelLow)) * 100) : null
  const entryReady = validInputs && target != null && current != null && target !== current && target !== 0
  const positionManaged = target != null && current != null && target === current && current !== 0
  const exitTriggerPrice = current === 1 ? exitChannelLow : current === -1 ? exitChannelHigh : null
  const distanceToExit = close != null && close > 0 && exitTriggerPrice != null
    ? Math.max(0, current === 1 ? ((close - exitTriggerPrice) / close) * 100 : ((exitTriggerPrice - close) / close) * 100)
    : null
  const orderAttempted = /^(OPEN|CLOSE)_/.test(orderStatus)
  const executed = orderStatus.endsWith('_OK')
  const executionBlocked = orderAttempted && !executed
  let selectionStatus = 'DISCARDED'
  let reasonCode = 'NO_BREAKOUT'
  let reason = trend === 'BULLISH'
    ? 'Tendencia alcista; espera ruptura del techo'
    : trend === 'BEARISH'
      ? 'Tendencia bajista; espera ruptura del piso'
      : 'Datos insuficientes para evaluar'
  if (!validInputs) {
    reasonCode = 'NO_DATA'
  } else if (orderStatus === 'WAIT_SESSION') {
    selectionStatus = 'EXECUTION_BLOCKED'
    reasonCode = 'WAIT_SESSION'
    reason = 'Espera apertura de sesión y cotización reciente; revalidará la decisión'
  } else if (orderStatus.startsWith('RISK_')) {
    selectionStatus = 'EXECUTION_BLOCKED'
    reasonCode = orderStatus
    const riskReasons: Record<string, string> = {
      UNPROTECTED_ACCOUNT_POSITION: 'hay posiciones sin SL confirmado',
      QUOTE_UNAVAILABLE: 'la cotización no es reciente o no es válida',
      ATR_UNAVAILABLE: 'faltan datos para calcular el ATR',
      MINIMUM_VOLUME_EXCEEDS_BUDGET: 'el volumen mínimo supera el presupuesto',
      RISK_HALT_REVIEW_REQUIRED: 'la recuperación de protección requiere revisión',
      UNKNOWN_ACCOUNT_RISK: 'no se puede calcular el riesgo de la cuenta',
      PENDING_ACCOUNT_ORDER: 'hay una orden pendiente en la cuenta',
      STOP_PENDING_EXECUTION: 'hay un SL pendiente de ejecución',
    }
    reason = orderStatus === 'RISK_OBSERVE' ? 'Política en observación; no abre nuevas posiciones'
      : `Entrada bloqueada por riesgo: ${riskReasons[orderMessage] ?? (orderMessage || 'verificar presupuesto y protección')}`
  } else if (executed) {
    selectionStatus = 'EXECUTED'
    reasonCode = 'EXECUTED'
    reason = 'Señal aprobada y orden ejecutada'
  } else if (executionBlocked) {
    selectionStatus = 'EXECUTION_BLOCKED'
    reasonCode = orderMessage.toLowerCase().includes('market closed') ? 'MARKET_CLOSED' : 'ORDER_REJECTED'
    reason = orderMessage ? `Señal aprobada; ejecución detenida: ${orderMessage}` : 'Señal aprobada; la orden no fue aceptada'
  } else if (entryReady) {
    selectionStatus = 'ENTRY_READY'
    reasonCode = 'ENTRY_READY'
    reason = `Ruptura ${potentialDirection === 'BUY' ? 'alcista' : 'bajista'} confirmada; entrada lista`
  } else if (positionManaged) {
    selectionStatus = 'MANAGING_POSITION'
    reasonCode = 'HOLD_POSITION'
    reason = 'La posición sigue abierta; no se ha activado la salida Donchian'
  }
  return {
    selection_status: selectionStatus,
    reason_code: reasonCode,
    discard_reason: reason,
    valid_inputs: validInputs,
    trend,
    potential_direction: potentialDirection,
    entry_ready: entryReady,
    order_attempted: orderAttempted,
    executed,
    close,
    sma,
    channel_high: channelHigh,
    channel_low: channelLow,
    exit_channel_high: exitChannelHigh,
    exit_channel_low: exitChannelLow,
    exit_trigger_price: exitTriggerPrice,
    distance_to_exit_pct: distanceToExit,
    exit_rule: current === 1
      ? 'Cerrar si la vela termina por debajo del canal de salida'
      : current === -1
        ? 'Cerrar si la vela termina por encima del canal de salida'
        : null,
    server_sl: 0,
    server_tp: 0,
    trigger_price: triggerPrice,
    distance_to_trigger_pct: distanceToTrigger,
    channel_position_pct: channelPosition,
  }
}

async function v5Overview(env: Env): Promise<Response> {
  const snapshot = await v5SnapshotRows(env)
  if (!snapshot.ok) return snapshot.response
  const data = snapshot.rows[0]
  if (!data || !Array.isArray(data.lifecycle) || !Array.isArray(data.signals) || !Array.isArray(data.trades)) {
    return json({ ok: false, error: 'Invalid dashboard snapshot' }, 502)
  }
  let signalRows: Array<Record<string, unknown>> = (data.signals as Array<Record<string, unknown>>).map((row) => ({ ...row, raw_payload: parseRawPayload(row.raw_payload) }))
  let tradeRows: Array<Record<string, unknown>> = (data.trades as Array<Record<string, unknown>>).map((row) => ({ ...row, raw_payload: parseRawPayload(row.raw_payload) }))
  const lifecycleRows: Array<Record<string, unknown>> = (data.lifecycle as Array<Record<string, unknown>>).map((row) => ({ ...row, raw_payload: parseRawPayload(row.raw_payload) }))
  const latestLifecycle = lifecycleRows[0] ?? null
  const latestRuntime = parseRawPayload(latestLifecycle?.raw_payload)
  const modern = latestRuntime?.telemetry_contract === 'snapshot-v53'
  const sleeveSnapshots = modern && Array.isArray(latestRuntime?.sleeves) ? latestRuntime.sleeves as Record<string, unknown>[] : []
  if (modern) {
    const history = Array.isArray(latestRuntime?.analysis_events) ? latestRuntime.analysis_events as Record<string, unknown>[] : []
    const current: Record<string, unknown>[] = sleeveSnapshots.filter(s => s.analysis && typeof s.analysis === 'object').map(s => ({ ...(s.analysis as Record<string, unknown>), observed_at: s.evaluated_at }))
    signalRows = [...history, ...current].sort((a,b) => Date.parse(String(b.observed_at)) - Date.parse(String(a.observed_at))).map(a => ({ symbol: a.symbol, created_at: a.observed_at, raw_payload: a }))
    tradeRows = (Array.isArray(latestRuntime?.trades) ? latestRuntime.trades as Record<string, unknown>[] : []).map(t => ({...t,raw_payload:t}))
  }
  // Only actual observation time establishes liveness, never a replay's reception.
  const latestContactMs = Date.parse(String(modern ? latestRuntime?.observed_at : latestLifecycle?.created_at ?? '')) || 0
  const nowMs = Date.now()
  const ageMinutes = latestContactMs > 0 ? Math.max(0, (nowMs - latestContactMs) / 60000) : null
  const stopped = latestRuntime?.runtime_event === 'deinit' || latestLifecycle?.event === 'ea_deinit'
  // Modern local capture is bounded to one minute. Do not keep a stopped relay
  // looking live for the legacy 35-minute heartbeat window.
  const boundedCapture = modern && latestRuntime?.visibility?.local_capture === true
  const observationMaxAgeSeconds = boundedCapture ? 180 : 35 * 60
  const runtimeRecent = ageMinutes != null && ageMinutes <= observationMaxAgeSeconds / 60 && latestContactMs <= nowMs + 120000 && !stopped
  const brokerConnected = latestRuntime?.terminal_connected !== false && String(latestRuntime?.terminal_connected ?? 'true') !== 'false'
  const online = runtimeRecent && brokerConnected
  const ledgerOpenPositions = tradeRows.filter((row) => row.close_time == null && row.event_type === 'open')

  const managedPositionId = finiteNumber(latestRuntime?.managed_position_id)
  const managedPositionOpenPrice = finiteNumber(latestRuntime?.managed_position_open_price)
  const managedPositionLots = finiteNumber(latestRuntime?.managed_position_lots)
  const managedPositionMagic = finiteNumber(latestRuntime?.managed_position_magic)
  const managedPositionSymbol = String(latestRuntime?.managed_position_symbol ?? '')
  const managedPositionDirection = String(latestRuntime?.managed_position_direction ?? '').toLowerCase()
  const managedPositionOpenTime = latestRuntime?.managed_position_open_time ?? null

  const runtimeOpenPositions: Record<string, unknown>[] =
    runtimeRecent && managedPositionId != null && managedPositionId > 0 && managedPositionSymbol
      ? [{
          source: 'MT5_RUNTIME_SNAPSHOT',
          symbol: managedPositionSymbol,
          position_id: managedPositionId,
          ticket: managedPositionId,
          direction: managedPositionDirection,
          open_time: managedPositionOpenTime,
          open_price: managedPositionOpenPrice,
          lots: managedPositionLots,
          magic_number: managedPositionMagic,
          close_time: null,
          event_type: 'open',
          ea_version: V5_EA_VERSION,
          execution_mode: 'DEMO',
          strategy_variant: V5_STRATEGY_VARIANT,
          account_login: finiteNumber(latestLifecycle?.account_login ?? latestRuntime?.account_login),
          account_environment: String(latestLifecycle?.account_environment ?? latestRuntime?.account_environment ?? 'UNKNOWN'),
          raw_payload: latestRuntime,
        }]
      : []

  const authoritativePositions: Record<string, unknown>[] | null = modern && Array.isArray(latestRuntime?.positions) ? (latestRuntime.positions as Record<string, unknown>[]).map(p => ({ ...p, source:'MT5_HISTORY_SNAPSHOT', raw_payload:p })) : null
  const openPositions = authoritativePositions ?? (runtimeRecent ? runtimeOpenPositions : ledgerOpenPositions)
  const metrics = modern && latestRuntime?.performance ? latestRuntime.performance as ReturnType<typeof performanceMetrics> : performanceMetrics(tradeRows)
  const reconciliation = modern ? latestRuntime?.reconciliation as Record<string, unknown> : {status:'UNVERIFIED',issues:['Historial anterior sin conciliación por cuenta']}
  const reconciled = reconciliation?.status === 'RECONCILED' 
  const cutoff24h = nowMs - 24 * 60 * 60 * 1000
  const recentSignals = signalRows.filter((row) => rowTime(row) >= cutoff24h && rowTime(row) <= nowMs + 120000 && (!modern || analysisIssue(parseRawPayload(row.raw_payload)) === null))
  const uniqueSignalMap = new Map<string, Record<string, unknown>>()
  for (const row of recentSignals) {
    const raw = parseRawPayload(row.raw_payload)
    const identity = String(raw?.signal_eval_id ?? `${row.symbol}-${raw?.timeframe ?? 'D1'}-${raw?.bar_time ?? row.bar_h4 ?? row.eval_time}`)
    const prior = uniqueSignalMap.get(identity)
    if (!prior || preferEvidence(parseRawPayload(prior.raw_payload) ?? {}, raw ?? {}) === raw) uniqueSignalMap.set(identity, row)
  }
  const uniqueRecentSignals = Array.from(uniqueSignalMap.values())
  const recentEvaluations = uniqueRecentSignals.map((row) => ({
    symbol: row.symbol,
    timeframe: String(parseRawPayload(row.raw_payload)?.timeframe ?? 'D1').toUpperCase(),
    sleeve: String(parseRawPayload(row.raw_payload)?.sleeve ?? 'CORE_D1'),
    evaluated_at: row.created_at ?? row.eval_time,
    ...decisionEvaluation(row),
  }))
  const entrySignals24h = recentEvaluations.filter(row => row.entry_ready).length
  const externalExperts = modern && Array.isArray(latestRuntime?.external_experts)
    ? (latestRuntime.external_experts as unknown[])
      .filter((row): row is Record<string, unknown> => row !== null && typeof row === 'object' && !Array.isArray(row))
      .map(row => {
        const observed = Date.parse(String(row.observed_at ?? ''))
        if (row.status === 'OBSERVING' && (!Number.isFinite(observed) || nowMs - observed > 120000 || observed > nowMs + 120000)) {
          return { ...row, status: 'STALE', reported_status: 'OBSERVING' }
        }
        return row
      }) : []
  const rejectedOrders = uniqueRecentSignals.filter((row) => {
    const raw = parseRawPayload(row.raw_payload)
    return String(raw?.order_status ?? '').includes('FAIL')
  })

  const timeframeOf = (row: Record<string, unknown>) => String(parseRawPayload(row.raw_payload)?.timeframe ?? 'D1').toUpperCase()
  const sleeveOf = (row: Record<string, unknown>) => String(parseRawPayload(row.raw_payload)?.sleeve ?? 'CORE_D1')
  const bySymbol = V5_SLEEVES.map((definition) => {
    const latest = signalRows.find((row) => row.symbol === definition.symbol && timeframeOf(row) === definition.timeframe && (!modern || analysisIssue(parseRawPayload(row.raw_payload)) === null)) ?? null
    const raw = parseRawPayload(latest?.raw_payload)
    const target = finiteNumber(raw?.target_position)
    const current = finiteNumber(raw?.current_position)
    const sleeveTrades = tradeRows.filter((row) => row.symbol === definition.symbol && timeframeOf(row) === definition.timeframe)
    const summaries = latestRuntime?.sleeve_performance as Record<string, ReturnType<typeof performanceMetrics>> | undefined
    const symbolMetrics = modern && summaries?.[definition.symbol+'-'+definition.timeframe] || performanceMetrics(sleeveTrades)
    const health = sleeveSnapshots.find(s => s.symbol===definition.symbol && s.timeframe===definition.timeframe)
    const livePosition = openPositions.find(p => p.symbol===definition.symbol && String(parseRawPayload(p.raw_payload)?.timeframe ?? 'D1')===definition.timeframe)
    return {
      ...definition,
      ...decisionEvaluation(latest),
      server_sl: finiteNumber(livePosition?.sl) ?? 0,
      server_tp: finiteNumber(livePosition?.tp) ?? 0,
      analysis_health: stopped ? 'STOPPED' : !runtimeRecent ? 'STALE' : !health ? 'UNVERIFIED' : health.data_issue ? 'DATA_REVIEW' : health.coverage_ok !== true ? 'PENDING' : health.session_open !== true ? 'MARKET_CLOSED' : health.feed_ok !== true ? 'FEED_STALE' : 'CURRENT',
      coverage_ok: health?.coverage_ok === true && !health?.data_issue,
      data_issue: health?.data_issue ?? null,
      feed_ok: health?.feed_ok === true,
      session_open: health?.session_open ?? null,
      quote_age_seconds: health?.tick_age_seconds ?? null,
      current_wait_reason: !runtimeRecent || stopped ? 'STALE_OBSERVATION' : health?.session_open === false ? 'SESSION_CLOSED' : health?.session_open === true && health?.feed_ok === false ? 'QUOTE_NOT_FRESH' : null,
      expected_bar: health?.expected_bar ?? null,
      spread_points: health?.spread_points ?? null,
      effective_lots: health?.effective_lots ?? null,
      contract_size: health?.contract_size ?? null,
      tick_value: health?.tick_value ?? null,
      profit_currency: health?.profit_currency ?? null,
      entry_lookback: health?.entry_lookback ?? null,
      exit_lookback: health?.exit_lookback ?? null,
      sma_period: health?.sma_period ?? null,
      signal: target === 1 ? 'BUY' : target === -1 ? 'SELL' : target === 0 ? 'FLAT' : 'UNKNOWN',
      position: current === 1 ? 'LONG' : current === -1 ? 'SHORT' : current === 0 ? 'FLAT' : 'UNKNOWN',
      last_bar: raw?.bar_time ?? latest?.bar_h4 ?? null,
      last_update: latest?.created_at ?? null,
      order_status: raw?.order_status ?? 'NO_DATA',
      order_message: raw?.order_message ?? null,
      closed_trades: symbolMetrics.closed_trades,
      realized_pnl: symbolMetrics.realized_pnl,
      profit_factor: symbolMetrics.profit_factor,
      win_rate: symbolMetrics.win_rate,
    }
  })
  const profitableSymbols = new Set(bySymbol.filter((row) => row.realized_pnl > 0).map((row) => row.symbol)).size
  const gateChecks = {
    sample: metrics.closed_trades >= V5_GATE_TRADES,
    profit_factor: metrics.profit_factor != null && metrics.profit_factor > 1.15,
    expectancy: metrics.expectancy != null && metrics.expectancy > 0,
    diversification: profitableSymbols >= 2,
    execution_quality: reconciled && tradeRows.some(t => t.position_id != null && t.open_time != null),
  }
  const gatePassed = Object.values(gateChecks).every(Boolean)
  const decision = metrics.closed_trades < V5_GATE_TRADES
    ? 'COLLECTING_EVIDENCE'
    : gatePassed
      ? 'READY_FOR_RISK_DESIGN'
      : 'REVIEW_STRATEGY'

  const riskHistory = modern ? await portfolioRiskHistory(env, latestRuntime ?? {}) : null
  return json({
    ok: true,
    generated_at: new Date(nowMs).toISOString(),
    environment: 'DEMO',
    expert: {
      name: 'Portfolio Trend',
      version: modern ? latestRuntime?.release_id : V5_EA_VERSION,
      strategy: 'Core D1 20/10/200 + experimental H4 60/30/600',
      timeframe: 'D1 + H4',
      symbols: V5_SYMBOLS,
    },
    operational: {
      status: stopped ? 'EXPERT_STOPPED' : online ? 'ONLINE' : runtimeRecent ? 'BROKER_OFFLINE' : latestContactMs > 0 ? 'STALE' : 'NO_TELEMETRY',
      market_state: modern && sleeveSnapshots.length > 0 && sleeveSnapshots.every(s => s.session_open === false) ? 'CLOSED' : 'OPEN_OR_UNKNOWN',
      latest_contact: latestContactMs > 0 ? new Date(latestContactMs).toISOString() : null,
      age_minutes: ageMinutes,
      last_event: latestRuntime?.runtime_event ?? latestLifecycle?.event ?? null,
      broker_connected: latestContactMs > 0 ? brokerConnected : null,
      open_positions: openPositions.length,
      rejected_orders_24h: rejectedOrders.length,
      evaluations_24h: recentEvaluations.length,
      entry_signals_24h: entrySignals24h,
      // Compatibility alias now means entry setups, never neutral evaluations.
      signals_24h: entrySignals24h,
      activity_window: { hours: 24, time_basis: 'UTC_OBSERVATION_TIME', scope: 'AVAILABLE_DEDUPLICATED_EVALUATIONS', future_clock_tolerance_seconds: 120 },
    },
    account: {
      login: finiteNumber(latestLifecycle?.account_login ?? latestRuntime?.account_login),
      environment: String(latestLifecycle?.account_environment ?? latestRuntime?.account_environment ?? 'UNKNOWN'),
      balance: finiteNumber(latestRuntime?.balance ?? latestLifecycle?.balance),
      equity: finiteNumber(latestRuntime?.equity),
      floating_pnl: finiteNumber(latestRuntime?.floating_pnl),
      free_margin: finiteNumber(latestRuntime?.free_margin),
      leverage: finiteNumber(latestRuntime?.leverage),
    },
    performance: { ...metrics, max_drawdown: metrics.closed_trades ? metrics.max_drawdown : null },
    dashboard_version: 'research-evidence-20261027',
    research_evidence: modern ? publicResearchEvidence(latestRuntime?.research_evidence, nowMs) : null,
    visibility: modern ? latestRuntime?.visibility ?? null : null,
    account_risk: modern ? { ...(latestRuntime?.account_risk ?? {exposures:[],complete:false}), portfolio: buildPortfolioRisk(latestRuntime?.account_risk ?? null, latestRuntime ?? null, nowMs, riskHistory) } : null,
    external_experts: externalExperts,
    attribution: modern ? latestRuntime?.attribution ?? null : null,
    periods: modern ? latestRuntime?.periods ?? null : null,
    validation: {
      operational_health: online && bySymbol.every(s => s.coverage_ok && s.feed_ok) ? 'CURRENT' : 'REVIEW_REQUIRED',
      historical_execution: !reconciled ? 'REVIEW_REQUIRED' : gateChecks.execution_quality ? 'OBSERVED_RECONCILED' : 'NO_EXECUTION_EVIDENCE',
      economic_evidence: 'INSUFFICIENT_OR_UNVALIDATED',
    },
    kronos: modern ? latestRuntime?.kronos ?? null : null,
    asset_research: modern && Array.isArray(latestRuntime?.asset_research) ? latestRuntime.asset_research : [],
    demo_analysis: modern ? latestRuntime?.demo_analysis ?? null : null,
    shadow_review: modern ? latestRuntime?.shadow_review ?? null : null,
    weekly: modern ? latestRuntime?.weekly ?? null : null,
    protection: modern ? latestRuntime?.protection ?? { total: openPositions.length, sl_present: openPositions.filter(p => Number(p.sl) > 0).length, unprotected: openPositions.filter(p => !(Number(p.sl) > 0)).length, tp_policy: 'DONCHIAN_NO_FIXED_TP', observed_at: latestRuntime?.observed_at } : null,
    evidence: {
      feed_quality: modern ? latestRuntime?.feed_quality ?? [] : [],
      feed_quality_error: latestRuntime?.feed_quality_error ?? null,
      reconciliation,
      certified: reconciled, // Compatibility alias: accounting only, never statistical certification.
      accounting_reconciled: reconciled,
      observation_max_age_seconds: observationMaxAgeSeconds,
      analysis_current: online && bySymbol.every(s => s.coverage_ok && s.feed_ok),
      covered_sleeves: bySymbol.filter(s => s.coverage_ok).length,
      current_sleeves: online ? bySymbol.filter(s => s.coverage_ok && s.feed_ok).length : 0,
      analysis_quality: latestRuntime?.analysis_quality ?? null,
      total_sleeves: bySymbol.length,
      account_currency: latestRuntime?.account_currency ?? 'USD',
      broker: latestRuntime?.account_server ?? null,
      time_basis: modern ? 'Broker para operaciones; UTC para observación' : 'Horas históricas sin validar',
      history_archive: latestRuntime?.history_archive ?? null,
      archive_delivery: latestRuntime?.archive_delivery ?? null,
      archive_delivery_scope: modern ? 'SNAPSHOT_BEFORE_CURRENT_DELIVERY_ACK' : 'LEGACY_UNVERIFIED',
      trade_count_total: latestRuntime?.trade_count_total ?? tradeRows.length,
      equity_samples: modern ? latestRuntime?.equity_samples ?? [] : [],
      refresh_seconds: 30,
      write_interval_seconds: null,
      write_interval_note: 'Cadencia de la fuente no inferida del refresco de esta vista.',
      statistical_validation: '60 cierres es un hito de revisión; no certifica ventaja estadística',
    },
    symbols: bySymbol,
    positions: openPositions.slice(0, 20).map((row) => ({ ...row, timeframe: timeframeOf(row), sleeve: sleeveOf(row) })),
    recent_trades: tradeRows.slice(-12).reverse().map((row) => ({ ...row, timeframe: timeframeOf(row), sleeve: sleeveOf(row) })),
    decision_flow: {
      window_hours: 24,
      stages: {
        analyzed: recentEvaluations.length,
        valid_data: recentEvaluations.filter((row) => row.valid_inputs).length,
        entries_ready: recentEvaluations.filter((row) => row.entry_ready).length,
        orders_attempted: recentEvaluations.filter((row) => row.order_attempted).length,
        executed: recentEvaluations.filter((row) => row.executed).length,
      },
      discarded: recentEvaluations.filter((row) => row.selection_status === 'DISCARDED').length,
      managed_positions: recentEvaluations.filter((row) => row.selection_status === 'MANAGING_POSITION').length,
      reasons: Object.values(recentEvaluations.reduce((result, row) => {
        const currentReason = result[row.reason_code] ?? { code: row.reason_code, label: row.discard_reason, count: 0 }
        currentReason.count += 1
        result[row.reason_code] = currentReason
        return result
      }, {} as Record<string, { code: string; label: string; count: number }>)).sort((a, b) => b.count - a.count),
      evaluations: recentEvaluations.slice(0, 20),
    },
    evidence_plan: {
      core: 'USDJPY, USDCHF y XAUUSD en D1',
      experimental: 'XAUUSD y AMD en H4, Donchian 60/30 + SMA600',
      estimated_closures_per_year: 32,
      estimated_months_to_60: 23,
      basis: 'validación histórica con costos duplicados; requiere confirmación prospectiva demo',
    },
    gate: {
      target_trades: V5_GATE_TRADES,
      progress_pct: Math.min(100, (metrics.closed_trades / V5_GATE_TRADES) * 100),
      profitable_symbols: profitableSymbols,
      checks: gateChecks,
      decision,
      passed: gatePassed,
    },
  })
}

// Store successful shared dashboard snapshots at the edge; never cache errors.
// This endpoint already serves one project-wide read-only view, not per-user data.
const SNAPSHOT_TTL_SECONDS = 30
async function cachedV5Overview(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'GET') return json({ ok: false, error: 'Method not allowed' }, 405)
  const keyUrl = new URL(request.url)
  keyUrl.search = ''
  keyUrl.pathname = '/api/v5-overview/cache-research-evidence-20261027/' + new URL(env.SUPABASE_URL).hostname
  const cacheKey = new Request(keyUrl, { method: 'GET' })
  const edgeCache = typeof caches !== 'undefined' ? await caches.open('dashboard-research-evidence-20261027') : null
  const hit = edgeCache ? await edgeCache.match(cacheKey) : undefined
  if (hit) {
    const headers = new Headers(hit.headers)
    headers.set('cache-control', 'no-store')
    headers.set('x-dashboard-cache', 'HIT')
    return new Response(hit.body, { status: hit.status, headers })
  }
  const response = await v5Overview(env)
  if (response.ok && edgeCache) {
    const stored = response.clone()
    const headers = new Headers(stored.headers)
    headers.set('cache-control', `public, max-age=${SNAPSHOT_TTL_SECONDS}`)
    try {
      await edgeCache.put(cacheKey, new Response(stored.body, { status: stored.status, headers }))
    } catch {
      // A cache storage failure must not hide a valid live snapshot.
      console.warn('Dashboard snapshot cache write failed')
    }
  }
  response.headers.set('x-dashboard-cache', 'MISS')
  return response
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)

    if (url.pathname === '/api/health') {
      return json({
        ok: true,
        service: 'algo-trading-dashboard',
        build: '2026-10-27-research-evidence',
        mode: 'read-only',
        ts: new Date().toISOString(),
      })
    }

    if (url.pathname === '/api/open-positions') {
      return openPositions(env)
    }

    if (url.pathname === '/api/clean-edge-trades') {
      return cleanEdgeTrades(env)
    }

    if (url.pathname === '/api/excluded-trades') {
      return excludedTrades(env)
    }

    if (url.pathname === '/api/latest-trades') {
      return latestTrades(env)
    }

    if (url.pathname === '/api/latest-signals') {
      return latestSignals(env)
    }

    if (url.pathname === '/api/live-validation-signals') {
      return liveValidationSignals(env)
    }

    if (url.pathname === '/api/data-quality') {
      return dataQuality(env)
    }

    if (url.pathname === '/api/program-status') {
      return programStatus(env)
    }

    if (url.pathname === '/api/v5-overview') {
      return cachedV5Overview(request, env)
    }

    return env.ASSETS.fetch(request)
  },
}
