import test from 'node:test'
import assert from 'node:assert/strict'
import worker from './index.ts'
import {analysisIssue,preferEvidence} from './evidence.ts'
const env={ASSETS:{fetch:async()=>new Response('')},SUPABASE_URL:'https://test.supabase.co',SUPABASE_SERVICE_ROLE_KEY:'test'}
const evalRow=(status,extra={})=>({event:'signal_eval',symbol:'AMD',timeframe:'H4',signal_eval_id:'a',bar_time:'2026-09-17T16:00:00',eval_time:'2026-09-17T20:00:00',observed_at:new Date().toISOString(),current_position:0,target_position:1,close:548,channel_high:527,channel_low:440,sma:300,order_status:status,...extra})
async function get(raw){const old=globalThis.fetch;globalThis.fetch=async()=>Response.json([{lifecycle:[{event:'ea_init',raw_payload:raw}],signals:[],trades:[]}]);try{return await (await worker.fetch(new Request('https://test/api/v5-overview'),env)).json()}finally{globalThis.fetch=old}}
function state(){return {telemetry_contract:'snapshot-v53',release_id:'v5.4.1',observed_at:new Date().toISOString(),runtime_event:'heartbeat',terminal_connected:true,positions:[{symbol:'AMD',timeframe:'H4',sl:0,proposed_sl:500}],trades:[],sleeves:[],analysis_events:[],reconciliation:{status:'RECONCILED',issues:[]},weekly:{equity_change:-1214.64,return_pct:-1.2146}}}
test('stopped Expert overrides a recently connected broker; weekly and protection remain historical',async()=>{const s=state();s.runtime_event='deinit';const d=await get(s);assert.equal(d.operational.status,'EXPERT_STOPPED');assert.equal(d.evidence.current_sleeves,0);assert.equal(d.protection.sl_present,0);assert.equal(d.weekly.equity_change,-1214.64);assert.equal(d.expert.name,'Portfolio Trend');assert.equal(d.expert.version,'v5.4.1')})
test('historical AMD bars do not enter funnel; repeated observation preserves actual fill',async()=>{const s=state();s.analysis_events=[evalRow('ALREADY_EVALUATED'),evalRow('OPEN_OK'),evalRow('ALREADY_EVALUATED',{signal_eval_id:'old',bar_time:'2015-07-29T16:00:00'})];const d=await get(s);assert.equal(d.decision_flow.stages.analyzed,1);assert.equal(d.decision_flow.stages.executed,1)})
test('risk block remains technical signal but never becomes an order attempt',async()=>{const s=state();s.analysis_events=[evalRow('RISK_BLOCKED',{order_message:'QUOTE_UNAVAILABLE'})];const d=await get(s);assert.equal(d.decision_flow.stages.entries_ready,1);assert.equal(d.decision_flow.stages.orders_attempted,0);assert.match(d.decision_flow.reasons[0].label,/cotización/);assert.equal(d.decision_flow.evaluations[0].selection_status,'EXECUTION_BLOCKED')})
test('dates must be complete and old years are rejected',()=>{assert.equal(analysisIssue({}), 'MISSING_BAR_TIME');assert.equal(analysisIssue(evalRow('HOLD',{bar_time:'2015-01-01'})),'HISTORICAL_BAR');assert.equal(preferEvidence(evalRow('OPEN_OK'),evalRow('ALREADY_EVALUATED')).order_status,'OPEN_OK')})
test('demo research stays separate from execution and preserves missing statistics',async()=>{const s=state();s.release_id='v5.4.2';s.demo_analysis={statistics:{closed_trades:0,win_rate_interval_95:null},asset_research:[{symbol:'EURUSD',execution_enabled:false,status:'INSUFFICIENT_HISTORY'}],position_proposals:[]};const d=await get(s);assert.equal(d.demo_analysis.statistics.win_rate_interval_95,null);assert.equal(d.demo_analysis.asset_research[0].execution_enabled,false);assert.equal(d.expert.version,'v5.4.2');assert.equal(d.dashboard_version,'data-integrity-20261027')})
test('closed session is an explicit wait, not an attempted order',async()=>{const s=state();s.analysis_events=[evalRow('WAIT_SESSION')];const d=await get(s);assert.equal(d.decision_flow.stages.orders_attempted,0);assert.match(d.decision_flow.reasons[0].label,/apertura/);assert.equal(d.decision_flow.evaluations[0].selection_status,'EXECUTION_BLOCKED')})

test('Kronos remains read-only and missing forecasts stay absent',async()=>{const s=state();s.kronos={status:'STALE_BARS',execution_authority:'NONE',rows:[]};const d=await get(s);assert.equal(d.kronos.status,'STALE_BARS');assert.equal(d.kronos.execution_authority,'NONE');assert.deepEqual(d.kronos.rows,[])})

test('24h entry setups are not neutral evaluations and exclude old or future observations',async()=>{
 const s=state(),now=Date.now();
 const neutral=evalRow('FLAT',{signal_eval_id:'neutral',target_position:0});
 s.analysis_events=[neutral,{...neutral},evalRow('OBSERVE',{signal_eval_id:'entry'}),evalRow('OBSERVE',{signal_eval_id:'old',observed_at:new Date(now-25*3600000).toISOString()}),evalRow('OBSERVE',{signal_eval_id:'future',observed_at:new Date(now+3600000).toISOString()}),evalRow('OBSERVE',{signal_eval_id:'invalid',channel_high:null})];
 const d=await get(s);
 assert.equal(d.operational.evaluations_24h,3);
 assert.equal(d.operational.entry_signals_24h,1);
 assert.equal(d.operational.signals_24h,1);
 assert.equal(d.operational.activity_window.scope,'AVAILABLE_DEDUPLICATED_EVALUATIONS');
 assert.equal(d.decision_flow.stages.valid_data,2);
 const flat=state();flat.analysis_events=[neutral];
 const n=await get(flat);assert.equal(n.operational.evaluations_24h,1);assert.equal(n.operational.signals_24h,0);
});
