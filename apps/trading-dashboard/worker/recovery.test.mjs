import test from 'node:test'
import assert from 'node:assert/strict'
import worker from './index.ts'
const env={ASSETS:{fetch:async()=>new Response('asset')},SUPABASE_URL:'https://test.supabase.co',SUPABASE_ANON_KEY:'test-only'}

test('recovery includes v4441 while preserving earlier versions and marks deinit as stopped',async()=>{
 const original=globalThis.fetch
 globalThis.fetch=async(input)=>{
  const url=String(input)
  assert.match(url,/v4\.44\.1/)
  assert.match(url,/v4\.44\.0/)
  if(url.includes('/ea_events?'))return Response.json([{ea_version:'v4.44.1',event:'ea_deinit',created_at:'2026-08-28T13:52:51Z',execution_scope:{capital_enabled:true,order_send_allowed:true}}])
  return Response.json([])
 }
 try{
  const result=await (await worker.fetch(new Request('https://test/api/program-status'),env)).json()
  assert.equal(result.active_ea_version,'v4.44.1')
  assert.equal(result.lifecycle[0].observed_state,'STOPPED')
  assert.equal(result.lifecycle[0].order_send_allowed,true) // Historical contract retained, activity separated.
  assert.equal(result.strategy.length,4)
  assert.equal(result.program_decision.active_challenger,'V5_PORTFOLIO_DEMO')
  assert.equal(result.challengers[0].status,'DEMO_ACTIVE_FIRST_SIGNAL_MARKET_CLOSED')
 }finally{globalThis.fetch=original}
})

test('latest-signal scope reads the installed observational version',async()=>{
 const original=globalThis.fetch
 globalThis.fetch=async(input)=>{assert.match(String(input),/ea_version=eq\.v4\.44\.1/);return Response.json([])}
 try{assert.equal((await worker.fetch(new Request('https://test/api/latest-signals'),env)).status,200)}finally{globalThis.fetch=original}
})
