import { observabilityRequest } from './observability'
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
    .map((row) => ({ ...row, numeric_pnl: finiteNumber(row.pnl) }))
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
  const entryReady = target != null && current != null && target !== current && target !== 0
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
    reason = 'La posición vigente continúa alineada con el modelo'
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
  const [lifecycle, signals, trades] = await Promise.all([
    supabaseRows(
      env,
      `ea_events?select=created_at,event,symbol,ea_version,balance,terminal_time,execution_mode,execution_scope,account_login,account_environment,raw_payload&ea_version=eq.${V5_EA_VERSION}&order=created_at.desc&limit=100`,
    ),
    supabaseRows(
      env,
      `signal_evals?select=created_at,symbol,eval_time,bar_h4,decision,action,block_reason,direction,entry_price,ea_version,strategy_variant,raw_payload&ea_version=eq.${V5_EA_VERSION}&strategy_variant=eq.${V5_STRATEGY_VARIANT}&order=created_at.desc&limit=500`,
    ),
    supabaseRows(
      env,
      `trades?select=created_at,symbol,position_id,ticket,order_ticket,deal_ticket,direction,open_time,open_price,lots,close_time,close_price,pnl,close_reason,ea_version,event_type,execution_mode,strategy_variant,link_status,raw_payload&ea_version=eq.${V5_EA_VERSION}&strategy_variant=eq.${V5_STRATEGY_VARIANT}&order=created_at.asc&limit=1000`,
    ),
  ])

  if (!lifecycle.ok) return lifecycle.response
  if (!signals.ok) return signals.response
  if (!trades.ok) return trades.response

  const signalRows = signals.rows.map((row) => ({ ...row, raw_payload: parseRawPayload(row.raw_payload) }))
  const tradeRows = trades.rows.map((row) => ({ ...row, raw_payload: parseRawPayload(row.raw_payload) }))
  const lifecycleRows = lifecycle.rows.map((row) => ({ ...row, raw_payload: parseRawPayload(row.raw_payload) }))
  const latestLifecycle = lifecycleRows[0] ?? null
  const latestRuntime = parseRawPayload(latestLifecycle?.raw_payload)
  const allRows = [...lifecycleRows, ...signalRows, ...tradeRows]
  const latestContactMs = allRows.reduce((latest, row) => Math.max(latest, rowTime(row)), 0)
  const nowMs = Date.now()
  const ageMinutes = latestContactMs > 0 ? Math.max(0, (nowMs - latestContactMs) / 60000) : null
  const runtimeRecent = ageMinutes != null && ageMinutes <= 35 && latestLifecycle?.event !== 'ea_deinit'
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

  const openPositions = runtimeRecent ? runtimeOpenPositions : ledgerOpenPositions
  const metrics = performanceMetrics(tradeRows)
  const cutoff24h = nowMs - 24 * 60 * 60 * 1000
  const recentSignals = signalRows.filter((row) => rowTime(row) >= cutoff24h)
  const uniqueSignalMap = new Map<string, Record<string, unknown>>()
  for (const row of recentSignals) {
    const raw = parseRawPayload(row.raw_payload)
    const identity = String(raw?.signal_eval_id ?? `${row.symbol}-${raw?.timeframe ?? 'D1'}-${raw?.bar_time ?? row.bar_h4 ?? row.eval_time}`)
    if (!uniqueSignalMap.has(identity)) uniqueSignalMap.set(identity, row)
  }
  const uniqueRecentSignals = Array.from(uniqueSignalMap.values())
  const recentEvaluations = uniqueRecentSignals.map((row) => ({
    symbol: row.symbol,
    timeframe: String(parseRawPayload(row.raw_payload)?.timeframe ?? 'D1').toUpperCase(),
    sleeve: String(parseRawPayload(row.raw_payload)?.sleeve ?? 'CORE_D1'),
    evaluated_at: row.created_at ?? row.eval_time,
    ...decisionEvaluation(row),
  }))
  const rejectedOrders = uniqueRecentSignals.filter((row) => {
    const raw = parseRawPayload(row.raw_payload)
    return String(raw?.order_status ?? '').includes('FAIL')
  })

  const timeframeOf = (row: Record<string, unknown>) => String(parseRawPayload(row.raw_payload)?.timeframe ?? 'D1').toUpperCase()
  const sleeveOf = (row: Record<string, unknown>) => String(parseRawPayload(row.raw_payload)?.sleeve ?? 'CORE_D1')
  const bySymbol = V5_SLEEVES.map((definition) => {
    const latest = signalRows.find((row) => row.symbol === definition.symbol && timeframeOf(row) === definition.timeframe) ?? null
    const raw = parseRawPayload(latest?.raw_payload)
    const target = finiteNumber(raw?.target_position)
    const current = finiteNumber(raw?.current_position)
    const sleeveTrades = tradeRows.filter((row) => row.symbol === definition.symbol && timeframeOf(row) === definition.timeframe)
    const symbolMetrics = performanceMetrics(sleeveTrades)
    return {
      ...definition,
      ...decisionEvaluation(latest),
      signal: target === 1 ? 'BUY' : target === -1 ? 'SELL' : 'FLAT',
      position: current === 1 ? 'LONG' : current === -1 ? 'SHORT' : 'FLAT',
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
    execution_quality: rejectedOrders.length === 0,
  }
  const gatePassed = Object.values(gateChecks).every(Boolean)
  const decision = metrics.closed_trades < V5_GATE_TRADES
    ? 'COLLECTING_EVIDENCE'
    : gatePassed
      ? 'READY_FOR_RISK_DESIGN'
      : 'REVIEW_STRATEGY'

  return json({
    ok: true,
    generated_at: new Date(nowMs).toISOString(),
    environment: 'DEMO',
    expert: {
      name: 'Portfolio Trend v5.2',
      version: V5_EA_VERSION,
      strategy: 'Core D1 20/10/200 + experimental H4 60/30/600',
      timeframe: 'D1 + H4',
      symbols: V5_SYMBOLS,
    },
    operational: {
      status: online ? 'ONLINE' : runtimeRecent ? 'BROKER_OFFLINE' : latestContactMs > 0 ? 'STALE' : 'NO_TELEMETRY',
      latest_contact: latestContactMs > 0 ? new Date(latestContactMs).toISOString() : null,
      age_minutes: ageMinutes,
      last_event: latestRuntime?.runtime_event ?? latestLifecycle?.event ?? null,
      broker_connected: latestContactMs > 0 ? brokerConnected : null,
      open_positions: openPositions.length,
      rejected_orders_24h: rejectedOrders.length,
      signals_24h: uniqueRecentSignals.length,
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
    performance: metrics,
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)

    // Separate read-only observability API; existing routes remain untouched.
    const observed = await observabilityRequest(request, env)
    if (observed) return observed

    if (url.pathname === '/api/health') {
      return json({
        ok: true,
        service: 'algo-trading-dashboard',
        build: '2026-09-08-v5.2-amd-h4-dashboard',
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
      return v5Overview(env)
    }

    return env.ASSETS.fetch(request)
  },
}
