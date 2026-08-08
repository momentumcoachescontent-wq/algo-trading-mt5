type Env = {
  ASSETS: {
    fetch(request: Request): Promise<Response>
  }
  SUPABASE_URL: string
  SUPABASE_SERVICE_ROLE_KEY?: string
  SUPABASE_ANON_KEY?: string
}

const BUG_DATA_01_CUTOFF = '2026-05-10T15:55:00.000Z'
const ACTIVE_EA_VERSION = 'v4.44.0'
const ACTIVE_STRATEGY_VARIANT = 'stage10_usdjpy_buy_v4401_demo'
const STAGE10_VERSIONS = [ACTIVE_EA_VERSION, 'v4.43.0', 'v4.43.1'] as const

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
): Promise<{ ok: true; rows: Array<Record<string, unknown>> } | { ok: false; response: Response }> {
  const key = getSupabaseKey(env)

  if (!env.SUPABASE_URL) {
    return { ok: false, response: json({ ok: false, error: 'SUPABASE_URL missing' }, 500) }
  }

  if (!key) {
    return { ok: false, response: json({ ok: false, error: 'No Supabase key configured' }, 500) }
  }

  const response = await fetch(`${env.SUPABASE_URL}/rest/v1/${path}`, {
    method: 'GET',
    headers: supabaseHeaders(key),
  })

  if (!response.ok) {
    return {
      ok: false,
      response: json({
        ok: false,
        status: response.status,
        error: 'Supabase request failed',
        detail: await response.text().catch(() => ''),
        path,
      }, 500),
    }
  }

  return { ok: true, rows: await response.json() as Array<Record<string, unknown>> }
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
      `ea_events?select=created_at,event,symbol,ea_version,phase,request_id,guard_version,execution_mode,execution_scope,boot_id,terminal_time&symbol=eq.USDJPY&ea_version=in.(${versions})&order=created_at.desc&limit=20`,
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
    program_decision: {
      active_challenger: 'DEMO_LIVE_VALIDATION',
      stage10c_v443x: 'HALTED_NO_PROMOTION',
      worker_331: 'OBSERVABILITY_ONLY',
      stage10d: 'OFFLINE_RESEARCH',
    },
    lifecycle: latestLifecycle,
    strategy: STAGE10_VERSIONS.map((version) => strategySummary(version, signals.rows, trades.rows)),
    challengers: [
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)

    if (url.pathname === '/api/health') {
      return json({
        ok: true,
        service: 'algo-trading-dashboard',
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

    return env.ASSETS.fetch(request)
  },
}
