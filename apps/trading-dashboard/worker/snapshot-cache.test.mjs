import assert from 'node:assert/strict'
import test from 'node:test'
import worker from './index.ts'

const env = { ASSETS: { fetch: async () => new Response('asset') }, SUPABASE_URL: 'https://test.supabase.co', SUPABASE_SERVICE_ROLE_KEY: 'test-only' }

test('network outage returns a bounded truthful error, without caching or leaking details', async () => {
  const originalFetch = globalThis.fetch, originalCaches = globalThis.caches
  let stores = 0
  globalThis.caches = { open: async () => ({ match: async () => undefined, put: async () => { stores++ } }) }
  globalThis.fetch = async (_, options) => {
    assert.ok(options.signal instanceof AbortSignal)
    throw new Error('private upstream detail')
  }
  try {
    const response = await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)
    assert.equal(response.status, 503)
    const result = await response.json()
    assert.equal(result.ok, false)
    assert.equal(result.code, 'UPSTREAM_UNAVAILABLE')
    assert.equal(JSON.stringify(result).includes('private upstream'), false)
    assert.equal(stores, 0)
  } finally { globalThis.fetch = originalFetch; globalThis.caches = originalCaches }
})

test('100 dashboard reads reuse one snapshot; expires at thirty seconds and cannot bypass via query strings', async () => {
  const originalFetch = globalThis.fetch, originalCaches = globalThis.caches, originalNow = Date.now
  let now = originalNow(), calls = 0
  const entries = new Map()
  Date.now = () => now
  globalThis.caches = { open: async () => ({
    match: async request => {
      const entry = entries.get(request.url)
      return entry && entry.expires > now ? entry.response.clone() : undefined
    },
    put: async (request, response) => {
      assert.equal(response.headers.get('cache-control'), 'public, max-age=30')
      entries.set(request.url, { response, expires: now + 30000 })
    },
  }) }
  globalThis.fetch = async input => {
    calls++
    assert.match(String(input), /\/rpc\/dashboard_v5_snapshot$/)
    return Response.json([{ lifecycle: [], signals: [], trades: [] }])
  }
  try {
    const first = await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)
    assert.equal(first.headers.get('x-dashboard-cache'), 'MISS')
    const initialData = await first.json()
    for (let i = 0; i < 100; i++) {
      const cached = await worker.fetch(new Request(`https://dashboard.test/api/v5-overview?refresh=${i}`), env)
      assert.equal(cached.headers.get('x-dashboard-cache'), 'HIT')
      assert.equal(cached.headers.get('cache-control'), 'no-store')
      assert.equal((await cached.json()).generated_at, initialData.generated_at)
    }
    assert.equal(calls, 1)
    now += 30000
    assert.equal((await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)).headers.get('x-dashboard-cache'), 'MISS')
    assert.equal(calls, 2)
  } finally { globalThis.fetch = originalFetch; globalThis.caches = originalCaches; Date.now = originalNow }
})

test('failed snapshots are never cached or presented as successful data', async () => {
  const originalFetch = globalThis.fetch, originalCaches = globalThis.caches
  let calls = 0, stores = 0
  globalThis.caches = { open: async () => ({ match: async () => undefined, put: async () => { stores++ } }) }
  globalThis.fetch = async () => { calls++; return new Response('temporary failure', { status: 503 }) }
  try {
    for (let i = 0; i < 2; i++) {
      const response = await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)
      assert.equal(response.ok, false)
    }
    assert.equal(calls, 2)
    assert.equal(stores, 0)
  } finally { globalThis.fetch = originalFetch; globalThis.caches = originalCaches }
})
