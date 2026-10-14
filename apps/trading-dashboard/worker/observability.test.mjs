import assert from 'node:assert/strict'
import test from 'node:test'
import { observabilityRequest } from './observability.ts'

const env = { SUPABASE_URL: 'https://db.example.com', SUPABASE_SERVICE_ROLE_KEY: 'unit-test-only' }
const at = '2026-10-01T00:00:00Z'
const sampleSignal = { symbol: 'USDJPY', ea_version: 'v5.2.0', strategy_variant: 'portfolio_trend_v520',
  created_at: at, eval_time: at, decision: 'BLOCKED', block_reason: 'NO_BREAKOUT',
  raw_payload: { timeframe: 'D1', bar_time: at, close: 151.1, sma: 149.4 } }

async function withMock(fn, run) {
  const original = globalThis.fetch
  globalThis.fetch = fn
  try { await run() } finally { globalThis.fetch = original }
}
const request = (path, method = 'GET') =>
  new Request('https://dashboard.example.com' + path, { method })
const load = async (path, method) => {
  const result = await observabilityRequest(request(path, method), env)
  assert.ok(result)
  return { status: result.status, json: await result.json() }
}

test('non-observability path is not intercepted; writes are rejected', async () => {
  assert.equal(await observabilityRequest(request('/api/v5-overview'), env), null)
  const post = await load('/api/observability/summary', 'POST')
  assert.equal(post.status, 405)
})
test('rejects invalid query values and requires timeframe for candles', async () => {
  assert.equal((await load('/api/observability/summary?symbol=AA%29')).status, 400)
  assert.equal((await load('/api/observability/summary?timeframe=M1')).status, 400)
  assert.equal((await load('/api/observability/candles')).status, 400)
})
test('requires restricted server-side credentials, not browser anon key', async () => {
  const result = await observabilityRequest(request('/api/observability/assets'), {
    SUPABASE_URL: 'https://db.example.com',
  })
  assert.equal(result.status, 503)
})
test('counts unique evaluations, not duplicated webhook rows', async () => {
  await withMock(async input => {
    const url = String(input)
    assert.match(url, /^https:\/\/db.example.com\/rest\/v1\//)
    if (url.includes('/signal_evals?')) return Response.json([sampleSignal, { ...sampleSignal, created_at: '2026-10-01T00:00:01Z' }])
    if (url.includes('/trades?')) return Response.json([{ pnl: 12, close_time: '2026-10-02T00:00:00Z', raw_payload: { timeframe: 'D1' } }])
    if (url.includes('/ea_events?')) return Response.json([{ created_at: '2026-10-02T00:00:00Z', boot_id: 'one' }])
    throw Error('unexpected endpoint')
  }, async () => {
    const data = await load('/api/observability/summary?symbol=USDJPY&version=v5.2.0&timeframe=D1')
    assert.equal(data.status, 200)
    assert.equal(data.json.evaluations, 1)
    assert.equal(data.json.blocked, 1)
    assert.equal(data.json.closed_trades, 1)
    assert.equal(data.json.realized_pnl, 12)
    assert.equal(data.json.distinct_boot_ids, 1)
  })
})
test('timeline excludes other timeframe and does not leak raw payload', async () => {
  await withMock(async input => {
    if (String(input).includes('/signal_evals?')) return Response.json([sampleSignal, {
      ...sampleSignal, raw_payload: { timeframe: 'H4' }, created_at: '2026-10-02T00:00:00Z'
    }])
    return Response.json([])
  }, async () => {
    const data = await load('/api/observability/timeline?symbol=USDJPY&timeframe=D1')
    assert.equal(data.json.evaluations.length, 1)
    assert.equal(data.json.evaluations[0].sma, 149.4)
    assert.equal(JSON.stringify(data.json).includes('raw_payload'), false)
  })
})
test('candles return chronological rows, never synthetic prices', async () => {
  await withMock(async input => {
    assert.match(String(input), /observability_candles/)
    return Response.json([
      { bar_time: '2026-10-02T00:00:00Z', open: 101, high: 104, low: 98, close: 103, tick_volume: 10 },
      { bar_time: '2026-10-01T00:00:00Z', open: 100, high: 102, low: 99, close: 101, tick_volume: 9 },
    ])
  }, async () => {
    const data = await load('/api/observability/candles?symbol=USDJPY&timeframe=D1')
    assert.equal(data.json.rows[0].close, 101)
    assert.equal(data.json.rows[1].close, 103)
    assert.equal(data.json.source, 'MT5_PASSIVE_OHLC')
  })
})
