import { Hono } from 'hono'

type Bindings = {
  SUPABASE_URL: string
  SUPABASE_KEY: string
  EA_WEBHOOK_SECRET: string
}

const app = new Hono<{ Bindings: Bindings }>()

app.get('/trading/health', (c) => {
  return c.json({ ok: true, service: 'trading-api', ts: new Date().toISOString() })
})

app.post('/trading/webhook', async (c) => {
  const secret = c.req.header('X-EA-Secret')
  if (secret !== c.env.EA_WEBHOOK_SECRET) {
    return c.json({ error: 'unauthorized' }, 401)
  }

  const body = await c.req.json()

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
      event_type:  body.event
    })
  })

  if (!res.ok) {
    const err = await res.text()
    return c.json({ error: 'db_error', detail: err }, 500)
  }

  return c.json({ ok: true })
})

export default app
