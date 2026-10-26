import assert from 'node:assert/strict'
import test from 'node:test'
import worker from './index.ts'

const base = { ASSETS: { fetch: async () => new Response('asset') }, SUPABASE_URL: 'https://test.supabase.co', SUPABASE_ANON_KEY: 'existing-public-key' }
const request = () => new Request('https://dashboard.test/api/v5-overview')

test('existing anon key falls back from forbidden RPC to public telemetry and preserves genuine v546 snapshot', { concurrency: false }, async t => {
  const original = globalThis.fetch
  t.after(() => { globalThis.fetch = original })
  const calls = []
  const observed = new Date().toISOString()
  const runtime = { telemetry_contract: 'snapshot-v53', release_id: 'v5.4.6-demo-candidate', observed_at: observed,
    runtime_event: 'heartbeat', terminal_connected: true, account_login: 12, account_server: 'Demo', account_environment: 'DEMO',
    balance: 1000, equity: 1000, positions: [], sleeves: [], trades: [], analysis_events: [],
    performance: { closed_trades: 0, realized_pnl: 0, equity_curve: [], profit_factor: null, expectancy: null },
    reconciliation: { status: 'RECONCILED', issues: [] },
    external_experts: [{ id: 'hobbiecode_goldrush', status: 'WAITING_FOR_OBSERVER', performance: null }] }
  globalThis.fetch = async (input, options) => {
    const url = new URL(String(input)); calls.push(url)
    assert.equal(options.method, 'GET')
    assert.equal(options.headers.apikey, base.SUPABASE_ANON_KEY)
    assert.ok(options.signal instanceof AbortSignal)
    if (url.pathname.endsWith('/rpc/dashboard_v5_snapshot')) return new Response('private denied detail', { status: 403 })
    assert.equal(url.pathname.startsWith('/rest/v1/rpc/'), false)
    assert.equal(url.searchParams.get('ea_version'), 'eq.v5.2.0')
    if (url.pathname.endsWith('/ea_events')) return Response.json([{ created_at: observed, event: 'ea_init', raw_payload: runtime }])
    if (url.pathname.endsWith('/signal_evals') || url.pathname.endsWith('/trades')) return Response.json([])
    throw new Error('Unexpected private read')
  }
  const response = await worker.fetch(request(), base)
  assert.equal(response.status, 200)
  const data = await response.json()
  assert.equal(data.expert.version, runtime.release_id)
  assert.equal(data.operational.status, 'ONLINE')
  assert.deepEqual(data.external_experts, runtime.external_experts)
  assert.equal(calls.length, 4)
})

test('RPC server errors never trigger fallback and upstream text is redacted', { concurrency: false }, async t => {
  const original = globalThis.fetch; let calls = 0
  t.after(() => { globalThis.fetch = original })
  globalThis.fetch = async () => { calls++; return new Response('private host and credential detail', { status: 500 }) }
  const response = await worker.fetch(request(), base)
  assert.equal(response.status, 500)
  assert.equal(calls, 1)
  const body = await response.text()
  assert.equal(body.includes('private host'), false)
  assert.equal(body.includes('credential'), false)
  assert.equal(body.includes('detail'), false)
})

test('service role rejection never downgrades to public reads', { concurrency: false }, async t => {
  const original = globalThis.fetch; let calls = 0
  t.after(() => { globalThis.fetch = original })
  globalThis.fetch = async () => { calls++; return new Response('denied', { status: 401 }) }
  const response = await worker.fetch(request(), { ...base, SUPABASE_SERVICE_ROLE_KEY: 'existing-service-key' })
  assert.equal(response.status, 500)
  assert.equal(calls, 1)
})
