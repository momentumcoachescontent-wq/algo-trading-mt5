import assert from 'node:assert/strict'
import test from 'node:test'

import worker from './index.ts'


const env = {
  ASSETS: { fetch: async () => new Response('asset') },
  SUPABASE_URL: 'https://example.supabase.co',
  SUPABASE_ANON_KEY: 'test-key',
}


test('program status keeps lifecycle and economic evidence separate', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (input) => {
    const url = String(input)
    if (url.includes('/ea_events?')) {
      assert.doesNotMatch(url, /(?:select=[^&]*)(?:capital_enabled|order_send_allowed)/)
      return Response.json([
        {
          created_at: '2026-08-01T17:10:06Z',
          event: 'ea_init',
          symbol: 'USDJPY',
          ea_version: 'v4.43.0',
          execution_mode: 'REAL',
          execution_scope: {
            capital_enabled: true,
            order_send_allowed: true,
          },
          request_id: '0c32e2ae',
        },
      ])
    }
    if (url.includes('/signal_evals?')) {
      return Response.json([
        { ea_version: 'v4.43.0', bar_h4: '2026-08-01T08:00:00Z', decision: 'ENTRY_READY_SHADOW_ONLY_BLOCKED', action: 'ENTRY_READY', block_reason: 'shadow_only' },
        { ea_version: 'v4.43.0', bar_h4: '2026-08-01T12:00:00Z', decision: 'BLOCKED_BY_TECHNICAL_GUARD', block_reason: 'no_ema_touch_bull' },
        { ea_version: 'v4.43.1', bar_h4: '2026-08-01T08:00:00Z', decision: 'ENTRY_READY_SHADOW_ONLY_BLOCKED', action: 'ENTRY_READY' },
      ])
    }
    if (url.includes('/trades?')) {
      return Response.json([
        { ea_version: 'v4.43.0', event_type: 'close', close_time: '2026-07-21T00:00:00Z', pnl: 432.98 },
      ])
    }
    throw new Error(`unexpected request ${url}`)
  }

  try {
    const response = await worker.fetch(new Request('https://dashboard.test/api/program-status'), env)
    assert.equal(response.status, 200)
    const payload = await response.json()
    assert.equal(payload.program_decision.worker_331, 'OBSERVABILITY_ONLY')
    const v4430 = payload.strategy.find((row) => row.ea_version === 'v4.43.0')
    const v4431 = payload.strategy.find((row) => row.ea_version === 'v4.43.1')
    const v4440 = payload.strategy.find((row) => row.ea_version === 'v4.44.0')
    assert.equal(v4430.closed_trades, 1)
    assert.equal(v4430.economic_gate, 'INSUFFICIENT_SAMPLE')
    assert.equal(v4430.expectancy_pnl, 432.98)
    assert.equal(v4430.max_drawdown_pnl, 0)
    assert.equal(v4430.entry_ready, 1)
    assert.equal(v4430.blocked, 1)
    assert.equal(v4430.entry_ready + v4430.blocked + v4430.errors + v4430.other, v4430.evaluations)
    assert.equal(v4431.entry_ready, 1)
    assert.equal(payload.lifecycle[0].capital_enabled, true)
    assert.equal(payload.lifecycle[0].order_send_allowed, true)
    assert.equal(v4440.economic_gate, 'NO_ECONOMIC_SAMPLE')
    assert.equal(payload.challengers.find((row) => row.id === 'portfolio_trend_v500').status, 'DEMO_ACTIVE_FIRST_SIGNAL_MARKET_CLOSED')
    assert.equal(payload.challengers.find((row) => row.id === 'stage10d_donchian').status, 'OFFLINE_RESEARCH')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('program status safely normalizes lifecycle flags from JSON text', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (input) => {
    const url = String(input)
    if (url.includes('/ea_events?')) {
      return Response.json([
        {
          created_at: '2026-08-07T23:59:58Z',
          event: 'ea_init',
          symbol: 'USDJPY',
          ea_version: 'v4.43.0',
          execution_mode: 'SHADOW_ONLY',
          execution_scope: '{"capital_enabled":false,"order_send_allowed":false}',
        },
        {
          created_at: '2026-08-07T23:59:57Z',
          event: 'ea_init',
          symbol: 'USDJPY',
          ea_version: 'v4.43.1',
          execution_mode: 'SHADOW_ONLY',
          execution_scope: '{malformed',
        },
      ])
    }
    if (url.includes('/signal_evals?') || url.includes('/trades?')) return Response.json([])
    throw new Error(`unexpected request ${url}`)
  }

  try {
    const response = await worker.fetch(new Request('https://dashboard.test/api/program-status'), env)
    assert.equal(response.status, 200)
    const payload = await response.json()
    const v4430 = payload.lifecycle.find((row) => row.ea_version === 'v4.43.0')
    const v4431 = payload.lifecycle.find((row) => row.ea_version === 'v4.43.1')
    assert.deepEqual(v4430.execution_scope, {
      capital_enabled: false,
      order_send_allowed: false,
    })
    assert.equal(v4430.capital_enabled, false)
    assert.equal(v4430.order_send_allowed, false)
    assert.equal(v4431.execution_scope, null)
    assert.equal(v4431.capital_enabled, null)
    assert.equal(v4431.order_send_allowed, null)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('latest signals recover spread ATR from object or string raw payload without throwing', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => Response.json([
    { spread_atr_ratio: null, raw_payload: { spread_atr_ratio: 0.00966851 } },
    { spread_atr_ratio: null, raw_payload: '{"spread_atr_ratio":0.02}' },
    { spread_atr_ratio: null, raw_payload: '{malformed' },
  ])

  try {
    const response = await worker.fetch(new Request('https://dashboard.test/api/latest-signals'), env)
    const payload = await response.json()
    assert.equal(payload.rows[0].spread_atr_ratio, 0.00966851)
    assert.equal(payload.rows[1].spread_atr_ratio, 0.02)
    assert.equal(payload.rows[2].spread_atr_ratio, null)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('data quality accepts null direction for blocked rows and deduplicates a bar', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (input) => {
    const url = String(input)
    if (url.includes('/signal_evals?') && url.includes('limit=1')) {
      return Response.json([{ created_at: '2026-08-05T08:00:00Z', decision: 'BLOCKED', action: 'BLOCKED', raw_payload: {}, atr_h4: 1, distance_to_ema_atr: 1, trend_state: 'CHOPPY', volatility_state: 'TRANSITORIA', session: 'LONDON' }])
    }
    if (url.includes('/signal_evals?')) {
      const row = { created_at: '2026-08-05T08:00:00Z', symbol: 'USDJPY', bar_h4: '2026-08-05T04:00:00Z', ea_version: 'v4.44.0', strategy_variant: 'stage10_usdjpy_buy_v4401_demo', decision: 'BLOCKED', action: 'BLOCKED', direction: null, raw_payload: {}, atr_h4: 1, distance_to_ema_atr: 1, trend_state: 'CHOPPY', volatility_state: 'TRANSITORIA', session: 'LONDON' }
      return Response.json([row, row])
    }
    if (url.includes('/trades?')) return Response.json([])
    throw new Error(`unexpected request ${url}`)
  }
  try {
    const response = await worker.fetch(new Request('https://dashboard.test/api/data-quality'), env)
    const payload = await response.json()
    assert.equal(payload.summary.sampled_signal_rows, 2)
    assert.equal(payload.summary.unique_h4_evaluations, 1)
    assert.equal(payload.summary.duplicate_signal_rows, 1)
    assert.equal(payload.summary.live_incomplete_signal_evals, 0)
  } finally {
    globalThis.fetch = originalFetch
  }
})


test('health endpoint returns JSON without Supabase access', async () => {
  const response = await worker.fetch(new Request('https://dashboard.test/api/health'), env)
  assert.equal(response.status, 200)
  assert.match(response.headers.get('content-type') ?? '', /application\/json/)
  assert.equal((await response.json()).service, 'algo-trading-dashboard')
})
