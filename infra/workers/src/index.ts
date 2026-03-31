import { Hono } from 'hono'

type Bindings = {
  SUPABASE_URL: string
  SUPABASE_KEY: string       // service_role key — secret, no en wrangler.jsonc
  EA_WEBHOOK_SECRET: string  // string fijo que pones en el EA para autenticar
}

const app = new Hono<{ Bindings: Bindings }>()

// ── Health check ──────────────────────────────────────────
app.get('/trading/health', (c) => {
  return c.json({ ok: true, ts: new Date().toISOString() })
})

// ── Webhook principal — recibe eventos del EA ─────────────
app.post('/trading/webhook', async (c) => {

  // 1. Autenticación básica: header secreto que manda el EA
  const secret = c.req.header('X-EA-Secret')
  if (secret !== c.env.EA_WEBHOOK_SECRET) {
    return c.json({ error: 'unauthorized' }, 401)
  }

  // 2. Parsear payload del EA
  const body = await c.req.json<{
    event:      string   // 'trade_open' | 'trade_close' | 'circuit_break'
    ticket:     number
    symbol:     string
    direction:  string   // 'buy' | 'sell'
    open_price: number
    close_price?: number
    lots:       number
    sl:         number
    tp:         number
    pnl?:       number
    ea_version: string
    phase:      string   // 'P0' | 'P1' ...
  }>()

  // 3. Insertar en Supabase vía REST
  const res = await fetch(`${c.env.SUPABASE_URL}/rest/v1/trades`, {
    method: 'POST',
    headers: {
      'Content-Type':  'application/json',
      'apikey':        c.env.SUPABASE_KEY,
      'Authorization': `Bearer ${c.env.SUPABASE_KEY}`,
      'Prefer':        'return=minimal'
    },
    body: JSON.stringify({
      ticket:      body.ticket,
      symbol:      body.symbol,
      direction:   body.direction,
      open_price:  body.open_price,
      close_price: body.close_price ?? null,
      lots:        body.lots,
      sl:          body.sl,
      tp:          body.tp,
      pnl:         body.pnl ?? null,
      ea_version:  body.ea_version,
      phase:       body.phase,
      event:       body.event
    })
  })

  if (!res.ok) {
    const err = await res.text()
    return c.json({ error: 'db_error', detail: err }, 500)
  }

  return c.json({ ok: true })
})

export default app
