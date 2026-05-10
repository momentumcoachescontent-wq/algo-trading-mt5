type Env = {
  ASSETS: {
    fetch(request: Request): Promise<Response>
  }
  SUPABASE_URL: string
  SUPABASE_SERVICE_ROLE_KEY?: string
  SUPABASE_ANON_KEY?: string
}

const BUG_DATA_01_CUTOFF = '2026-05-10T15:55:00.000Z'

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
  'phase',
].join(',')

async function openPositions(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `trades?select=${tradeSelect}&close_time=is.null&exclude_from_edge=eq.false&order=open_time.desc&limit=50`,
  )
}

async function cleanEdgeTrades(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `trades?select=${tradeSelect}&exclude_from_edge=eq.false&order=created_at.desc&limit=50`,
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
  return supabaseGet(
    env,
    `signal_evals?select=${signalSelect}&order=created_at.desc&limit=50`,
  )
}

async function liveValidationSignals(env: Env): Promise<Response> {
  return supabaseGet(
    env,
    `signal_evals?select=${signalSelect}&created_at=gte.${encodeURIComponent(BUG_DATA_01_CUTOFF)}&order=created_at.desc&limit=100`,
  )
}

function isSignalIncomplete(row: Record<string, unknown>): boolean {
  return (
    row.raw_payload == null ||
    row.direction == null ||
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
      `${env.SUPABASE_URL}/rest/v1/signal_evals?select=${signalSelect}&created_at=gte.${encodeURIComponent(
        BUG_DATA_01_CUTOFF,
      )}&order=created_at.desc&limit=200`,
      { headers: supabaseHeaders(key) },
    ),
    fetch(
      `${env.SUPABASE_URL}/rest/v1/trades?select=${tradeSelect}&created_at=gte.${encodeURIComponent(
        BUG_DATA_01_CUTOFF,
      )}&order=created_at.desc&limit=200`,
      { headers: supabaseHeaders(key) },
    ),
    fetch(
      `${env.SUPABASE_URL}/rest/v1/signal_evals?select=${signalSelect}&order=created_at.desc&limit=1`,
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
  const latestSignal = latestSignalRows[0] ?? null

  const incompleteSignals = signals.filter(isSignalIncomplete)
  const incompleteTradeOpens = trades.filter(isOpenTradeIncomplete)
  const incompleteTradeCloses = trades.filter(isClosedTradeIncomplete)

  return json({
    ok: true,
    cutoff: BUG_DATA_01_CUTOFF,
    summary: {
      live_signal_evals_checked: signals.length,
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

    return env.ASSETS.fetch(request)
  },
}
