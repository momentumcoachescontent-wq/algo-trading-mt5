import { Hono } from 'hono'

type Bindings = {
  SUPABASE_URL: string
  SUPABASE_KEY: string
  EA_WEBHOOK_SECRET: string
}

const app = new Hono<{ Bindings: Bindings }>()

function json(c: any, body: unknown, status = 200) {
  return c.json(body, status)
}

// ── Middleware global de logging ──────────────────────────
app.use('*', async (c, next) => {
  const req = c.req.raw
  const url = new URL(req.url)
  const requestId =
    req.headers.get('cf-ray') ||
    crypto.randomUUID()

  c.set('requestId', requestId)

  console.log('[REQ]', JSON.stringify({
    requestId,
    method: req.method,
    path: url.pathname,
    search: url.search,
    userAgent: req.headers.get('user-agent'),
    contentType: req.headers.get('content-type'),
    contentLength: req.headers.get('content-length'),
  }))

  const started = Date.now()

  await next()

  console.log('[RES]', JSON.stringify({
    requestId,
    path: url.pathname,
    status: c.res.status,
    ms: Date.now() - started,
  }))
})

// ── Error handler global ──────────────────────────────────
app.onError((err, c) => {
  const requestId = c.get('requestId') || crypto.randomUUID()

  console.log('[UNCAUGHT]', JSON.stringify({
    requestId,
    error: String(err),
    stack: err?.stack || null,
    path: new URL(c.req.raw.url).pathname,
    method: c.req.raw.method,
  }))

  return c.json(
    {
      ok: false,
      requestId,
      error: 'worker_exception',
      detail: String(err),
    },
    500
  )
})

// ── Health check ──────────────────────────────────────────
app.get('/trading/health', (c) => {
  const requestId = c.get('requestId')

  console.log('[HEALTH_OK]', JSON.stringify({ requestId }))

  return c.json({
    ok: true,
    ts: new Date().toISOString(),
    requestId,
  })
})

// ── Test endpoint para MT5 POST ───────────────────────────
app.post('/trading/test', async (c) => {
  const requestId = c.get('requestId')
  const raw = await c.req.raw.clone().text()

  console.log('[TEST_RAW]', JSON.stringify({
    requestId,
    raw,
  }))

  return c.json({
    ok: true,
    route: 'test',
    requestId,
    received: raw,
  })
})

// ── Webhook principal — recibe eventos del EA ─────────────
app.post('/trading/webhook', async (c) => {
  const requestId = c.get('requestId')

  // 1. Autenticación básica
  const secret = c.req.header('X-EA-Secret')

  if (secret !== c.env.EA_WEBHOOK_SECRET) {
    console.log('[AUTH_FAIL]', JSON.stringify({
      requestId,
      provided: secret ? 'present' : 'missing',
    }))

    return c.json({ ok: false, requestId, error: 'unauthorized' }, 401)
  }

  // 2. Leer body crudo primero para poder loguearlo
  const raw = await c.req.raw.clone().text()

  console.log('[WEBHOOK_RAW]', JSON.stringify({
    requestId,
    raw,
  }))

  let body: {
    event: string
    ticket: number
    symbol: string
    direction: string
    open_price: number
    close_price?: number
    lots: number
    sl: number
    tp: number
    pnl?: number
    ea_version: string
    phase: string
  }

  try {
    body = JSON.parse(raw)
  } catch (e) {
    console.log('[WEBHOOK_JSON_PARSE_ERROR]', JSON.stringify({
      requestId,
      error: String(e),
      raw,
    }))

    return c.json(
      { ok: false, requestId, error: 'invalid_json' },
      400
    )
  }

  console.log('[WEBHOOK_PARSED]', JSON.stringify({
    requestId,
    event: body.event,
    ticket: body.ticket,
    symbol: body.symbol,
    direction: body.direction,
    pnl: body.pnl ?? null,
    ea_version: body.ea_version,
    phase: body.phase,
  }))

  // 3. Insertar en Supabase vía REST
  const res = await fetch(`${c.env.SUPABASE_URL}/rest/v1/trades`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'apikey': c.env.SUPABASE_KEY,
      'Authorization': `Bearer ${c.env.SUPABASE_KEY}`,
      'Prefer': 'return=minimal'
    },
    body: JSON.stringify({
      ticket: body.ticket,
      symbol: body.symbol,
      direction: body.direction,
      open_price: body.open_price,
      close_price: body.close_price ?? null,
      lots: body.lots,
      sl: body.sl,
      tp: body.tp,
      pnl: body.pnl ?? null,
      ea_version: body.ea_version,
      phase: body.phase,
      event: body.event
    })
  })

  if (!res.ok) {
    const err = await res.text()

    console.log('[SUPABASE_ERROR]', JSON.stringify({
      requestId,
      status: res.status,
      detail: err,
    }))

    return c.json(
      { ok: false, requestId, error: 'db_error', detail: err },
      500
    )
  }

  console.log('[WEBHOOK_OK]', JSON.stringify({
    requestId,
    ticket: body.ticket,
    symbol: body.symbol,
    event: body.event,
  }))

  return c.json({ ok: true, requestId })
})

export default app
