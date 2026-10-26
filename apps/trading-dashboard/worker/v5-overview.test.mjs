import assert from 'node:assert/strict'
import test from 'node:test'

import worker from './index.ts'

const env = {
  ASSETS: { fetch: async () => new Response('asset') },
  SUPABASE_URL: 'https://test.supabase.co',
  SUPABASE_ANON_KEY: 'test-only',
}

function snapshotFixture(handler) {
  return async (input) => {
    assert.match(String(input), /\/rpc\/dashboard_v5_snapshot$/)
    const lifecycle = await (await handler('https://test.supabase.co/ea_events?')).json()
    const signals = await (await handler('https://test.supabase.co/signal_evals?')).json()
    const trades = await (await handler('https://test.supabase.co/trades?')).json()
    return Response.json([{ lifecycle, signals, trades }])
  }
}

test('v5 overview separates operations, performance and promotion gate', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = snapshotFixture(async (input) => {
    const url = String(input)
    if (url.includes('/ea_events?')) {
      return Response.json([{
        created_at: new Date().toISOString(),
        event: 'ea_init',
        symbol: 'USDJPY',
        ea_version: 'v5.2.0',
        balance: 100120,
        raw_payload: {
          runtime_event: 'heartbeat',
          balance: 100120,
          equity: 100150,
          floating_pnl: 30,
          free_margin: 99800,
          leverage: 100,
          terminal_connected: true,
          account_login: 5055685180,
          account_environment: 'DEMO',
          open_positions: 1,
          managed_position_id: 58361907292,
          managed_position_symbol: 'USDJPY',
          managed_position_direction: 'SELL',
          managed_position_open_price: 153.615,
          managed_position_lots: 0.1,
          managed_position_magic: 2034814958,
          managed_position_open_time: '2026-09-09T05:03:25Z',
        },
      }])
    }
    if (url.includes('/signal_evals?')) {
      return Response.json([
        { created_at: new Date().toISOString(), symbol: 'USDJPY', raw_payload: { signal_eval_id: 'jpy-d1', timeframe: 'D1', sleeve: 'CORE_D1', target_position: -1, current_position: -1, order_status: 'HOLD', bar_time: '2026-09-05T00:00:00Z', close: 155, channel_high: 160, channel_low: 150, exit_channel_high: 157, exit_channel_low: 153, sma: 158 } },
        { created_at: new Date().toISOString(), symbol: 'USDCHF', raw_payload: { signal_eval_id: 'chf-d1', timeframe: 'D1', sleeve: 'CORE_D1', target_position: 0, current_position: 0, order_status: 'NO_ACTION', bar_time: '2026-09-05T00:00:00Z', close: 0.8, channel_high: 0.82, channel_low: 0.78, sma: 0.79 } },
        { created_at: new Date().toISOString(), symbol: 'XAUUSD', raw_payload: { signal_eval_id: 'xau-h4', timeframe: 'H4', sleeve: 'EXPERIMENTAL_H4', target_position: 1, current_position: 0, order_status: 'OPEN_OK', bar_time: '2026-09-05T04:00:00Z', close: 4700, channel_high: 4650, channel_low: 4200, sma: 4400 } },
      ])
    }
    if (url.includes('/trades?')) {
      return Response.json([
        { created_at: '2026-09-01T00:00:00Z', close_time: '2026-09-01T01:00:00Z', event_type: 'close', symbol: 'USDJPY', pnl: 100 },
        { created_at: '2026-09-02T00:00:00Z', close_time: '2026-09-02T01:00:00Z', event_type: 'close', symbol: 'USDJPY', pnl: -40 },
        { created_at: '2026-09-03T00:00:00Z', close_time: '2026-09-03T01:00:00Z', event_type: 'close', symbol: 'USDCHF', pnl: 60, raw_payload: { timeframe: 'D1', sleeve: 'CORE_D1' } },
        { created_at: '2026-09-04T00:00:00Z', close_time: '2026-09-04T01:00:00Z', event_type: 'close', symbol: 'XAUUSD', pnl: 20, raw_payload: { timeframe: 'H4', sleeve: 'EXPERIMENTAL_H4' } },
        { created_at: '2026-09-05T00:00:00Z', close_time: null, event_type: 'open', symbol: 'USDJPY', pnl: null },
      ])
    }
    throw new Error(`unexpected request ${url}`)
  })

  try {
    const response = await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)
    assert.equal(response.status, 200)
    const payload = await response.json()
    assert.equal(payload.operational.status, 'ONLINE')
    assert.equal(payload.operational.open_positions, 1)
    assert.equal(payload.positions.length, 1)
    assert.equal(payload.positions[0].source, 'MT5_RUNTIME_SNAPSHOT')
    assert.equal(payload.positions[0].position_id, 58361907292)
    assert.equal(payload.positions[0].symbol, 'USDJPY')
    assert.equal(payload.positions[0].direction, 'sell')
    assert.equal(payload.positions[0].open_price, 153.615)
    assert.equal(payload.positions[0].lots, 0.1)
    assert.equal(payload.positions[0].magic_number, 2034814958)
    assert.equal(payload.positions[0].account_login, 5055685180)
    assert.notEqual(payload.positions[0].position_id, 58357500400)
    assert.equal(payload.account.equity, 100150)
    assert.equal(payload.performance.closed_trades, 4)
    assert.equal(payload.performance.realized_pnl, 140)
    assert.equal(payload.performance.profit_factor, 4.5)
    assert.equal(payload.performance.max_drawdown, 40)
    assert.equal(payload.symbols.find((row) => row.symbol === 'USDJPY').signal, 'SELL')
    assert.equal(payload.symbols.find((row) => row.symbol === 'USDJPY').exit_trigger_price, 157)
    assert.equal(payload.symbols.find((row) => row.symbol === 'USDJPY').distance_to_exit_pct, (2 / 155) * 100)
    assert.equal(payload.symbols.find((row) => row.symbol === 'USDJPY').server_sl, 0)
    assert.equal(payload.symbols.find((row) => row.symbol === 'USDJPY').server_tp, 0)
    assert.equal(payload.symbols.find((row) => row.timeframe === 'H4').experimental, true)
    assert.equal(payload.evidence_plan.estimated_months_to_60, 23)
    assert.equal(payload.expert.version, 'v5.2.0')
    assert.equal(payload.symbols.find((row) => row.symbol === 'AMD').timeframe, 'H4')
    assert.equal(payload.decision_flow.stages.analyzed, 3)
    assert.equal(payload.decision_flow.stages.entries_ready, 1)
    assert.equal(payload.decision_flow.stages.orders_attempted, 1)
    assert.equal(payload.decision_flow.stages.executed, 1)
    assert.equal(payload.decision_flow.discarded, 1)
    assert.equal(payload.symbols.find((row) => row.symbol === 'USDCHF').trend, 'BULLISH')
    assert.match(payload.symbols.find((row) => row.symbol === 'USDCHF').discard_reason, /espera ruptura/)
    assert.equal(payload.gate.profitable_symbols, 3)
    assert.equal(payload.gate.decision, 'COLLECTING_EVIDENCE')
    assert.equal(payload.gate.passed, false)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('v5 overview distinguishes a running Expert from an offline broker', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = snapshotFixture(async (input) => {
    const url = String(input)
    if (url.includes('/ea_events?')) {
      return Response.json([{
        created_at: new Date().toISOString(),
        event: 'ea_init',
        ea_version: 'v5.2.0',
        raw_payload: { runtime_event: 'heartbeat', terminal_connected: false },
      }])
    }
    return Response.json([])
  })
  try {
    const payload = await (await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)).json()
    assert.equal(payload.operational.status, 'BROKER_OFFLINE')
    assert.equal(payload.operational.broker_connected, false)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('v5 overview reports no telemetry without fabricating performance', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = snapshotFixture(async () => Response.json([]))
  try {
    const payload = await (await worker.fetch(new Request('https://dashboard.test/api/v5-overview'), env)).json()
    assert.equal(payload.operational.status, 'NO_TELEMETRY')
    assert.equal(payload.performance.closed_trades, 0)
    assert.equal(payload.performance.profit_factor, null)
    assert.equal(payload.gate.progress_pct, 0)
  } finally {
    globalThis.fetch = originalFetch
  }
})
