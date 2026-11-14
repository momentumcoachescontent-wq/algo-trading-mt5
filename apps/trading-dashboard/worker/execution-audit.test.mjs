import test from 'node:test'
import assert from 'node:assert/strict'
import { publicExecutionAudit } from './execution-audit.ts'
import worker from './index.ts'

test('execution audit allowlists public fields and retains missing values', () => {
  const row = publicExecutionAudit({schema_version:1, account_login:'private', rows:[{symbol:'XAUUSD',requested_sl:4000,requested_tp:4060,account_login:'private',secret:'private',fill_confirmed:false,fill_price:4020}]})
  assert.equal(row.account_login,undefined);assert.equal(row.rows[0].secret,undefined)
  assert.equal(row.rows[0].requested_tp,4060);assert.equal(row.rows[0].fill_price,null)
  assert.equal(row.requests_24h,null)
})

test('a claimed fill without deal ID is not presented as confirmed', () => {
  const row=publicExecutionAudit({schema_version:1, rows:[{fill_confirmed:true,fill_price:4020}]})
  assert.equal(row.rows[0].fill_confirmed,false);assert.equal(row.rows[0].fill_price,null)
  assert.equal(publicExecutionAudit(null),null);assert.equal(publicExecutionAudit({schema_version:2}),null)
})

test('bounded confirmed evidence preserves broker IDs and prices', () => {
  const row=publicExecutionAudit({schema_version:1,rows:Array.from({length:30},()=>({fill_confirmed:true,broker_deal_ticket:'7',fill_price:4020}))})
  assert.equal(row.rows.length,25);assert.equal(row.rows[0].broker_deal_ticket,'7');assert.equal(row.rows[0].fill_price,4020)
})

test('overview exposes audited requests and authoritative position SL/TP', async () => {
  const env={ASSETS:{fetch:async()=>new Response('')},SUPABASE_URL:'https://test.supabase.co',SUPABASE_SERVICE_ROLE_KEY:'test'}
  const now=new Date().toISOString()
  const raw={telemetry_contract:'snapshot-v53',release_id:'v5.5.0-demo-automation',observed_at:now,terminal_connected:true,
    reconciliation:{status:'RECONCILED',issues:[]},positions:[{symbol:'XAUUSD',sl:4000,tp:4060}],trades:[],sleeves:[],analysis_events:[],
    risk_policy:{sizing_mode:'FIXED_VOLUME_DEMO',per_trade_pct:.1,fixed_lots:.1,fixed_amd_lots:1,take_profit_r:2,portfolio_pct:100,gold_pct:100},
    performance:{closed_trades:0,realized_pnl:0},execution_audit:{schema_version:1,observed_at:now,requests_24h:1,
      rows:[{symbol:'XAUUSD',requested_sl:4000,requested_tp:4060,status:'RESULT_RECORDED_NO_FILL_PROOF',fill_confirmed:false}]}}
  const old=globalThis.fetch
  globalThis.fetch=async()=>Response.json([{lifecycle:[{event:'ea_init',created_at:now,raw_payload:raw}],signals:[],trades:[]}])
  try {
    const data=await (await worker.fetch(new Request('https://test/api/v5-overview'),env)).json()
    assert.equal(data.execution_audit.rows[0].requested_tp,4060)
    assert.equal(data.execution_audit.rows[0].fill_confirmed,false)
    assert.equal(data.positions[0].sl,4000);assert.equal(data.positions[0].tp,4060)
    assert.equal(data.execution_policy.per_trade_pct,null);assert.equal(data.execution_policy.fixed_lots,.1)
    assert.equal(data.execution_policy.fixed_amd_lots,1);assert.equal(data.execution_policy.take_profit_r,2)
  } finally { globalThis.fetch=old }
})
