import test from 'node:test'
import assert from 'node:assert/strict'
import worker from './index.ts'
const env={ASSETS:{fetch:async()=>new Response('')},SUPABASE_URL:'https://test.supabase.co',SUPABASE_SERVICE_ROLE_KEY:'test'}
function state(){return {telemetry_contract:'snapshot-v53',release_id:'v5.3.0',observed_at:new Date().toISOString(),terminal_connected:true,reconciliation:{status:'RECONCILED',issues:[]},positions:[{symbol:'XAUUSD',timeframe:'H4',position_id:1,sl:4200},{symbol:'AMD',timeframe:'H4',position_id:2}],trades:[],performance:{closed_trades:0,wins:0,losses:0,realized_pnl:0,profit_factor:null,expectancy:null,win_rate:null,max_drawdown:null,equity_curve:[]},sleeves:[{symbol:'XAUUSD',timeframe:'H4',coverage_ok:true,feed_ok:true,session_open:false,evaluated_at:new Date().toISOString(),analysis:{symbol:'XAUUSD',timeframe:'H4',signal_eval_id:'x',bar_time:'2026-09-11T16:00:00',current_position:1,target_position:1,close:4300,channel_high:4400,channel_low:4200,exit_channel_low:4250,exit_channel_high:4380,sma:4200}}],analysis_events:[]}}
async function get(raw){let calls=0;const old=globalThis.fetch;globalThis.fetch=async()=>{calls++;return Response.json([{lifecycle:[{event:'ea_init',created_at:new Date().toISOString(),raw_payload:raw}],signals:[],trades:[{symbol:'USDJPY',pnl:999,close_time:'2026-09-01'}]}])};try{const response=await worker.fetch(new Request('https://test/api/v5-overview'),env);assert.equal(calls,1);return await response.json()}finally{globalThis.fetch=old}}
test('v53 uses full positions and current account history, not unrelated legacy PnL',async()=>{const d=await get(state());assert.equal(d.positions.length,2);assert.equal(d.positions[0].timeframe,'H4');assert.equal(d.performance.realized_pnl,0);assert.equal(d.performance.max_drawdown,null);assert.equal(d.expert.version,'v5.3.0');assert.equal(d.symbols.find(s=>s.symbol==='XAUUSD'&&s.timeframe==='H4').server_sl,4200);assert.equal(d.gate.checks.execution_quality,false)})
test('replayed snapshots do not fake current connectivity',async()=>{const s=state();s.observed_at='2020-01-01T00:00:00Z';const d=await get(s);assert.equal(d.operational.status,'STALE');assert.equal(d.evidence.analysis_current,false)})
test('weekend distinguishes closed market and preserved analysis',async()=>{const d=await get(state());assert.equal(d.symbols.find(s=>s.symbol==='XAUUSD'&&s.timeframe==='H4').analysis_health,'MARKET_CLOSED')})

test('historical fills remain evidence without an order in the last day',async()=>{
 const s=state();s.trades=[{position_id:42,symbol:'USDJPY',open_time:'2026-08-01T00:00:00',close_time:'2026-08-02T00:00:00',pnl:-5}];
 const d=await get(s);assert.equal(d.gate.checks.execution_quality,true);assert.equal(d.validation.historical_execution,'OBSERVED_RECONCILED');assert.equal(d.validation.operational_health,'REVIEW_REQUIRED');assert.equal(d.validation.economic_evidence,'INSUFFICIENT_OR_UNVALIDATED');
});
test('cohorts and periods preserve missing provenance and period values',async()=>{
 const s=state();s.attribution={groups:[{entry_release_id:null,provenance_status:'UNKNOWN_LEGACY'}]};s.periods={month:{return_pct:null}};
 const d=await get(s);assert.equal(d.attribution.groups[0].entry_release_id,null);assert.equal(d.periods.month.return_pct,null);assert.equal(d.evidence.accounting_reconciled,true);
});

test('external expert evidence remains separate from PortfolioTrend performance',async()=>{
 const s=state();s.external_experts=[{id:'hobbiecode_goldrush',name:'HobbieCode GoldRush',status:'WAITING_FOR_IDENTITY',magic_number:null,performance:{realized_pnl:null},positions:[],issues:['IDENTITY_UNKNOWN']}];
 const d=await get(s);assert.deepEqual(d.external_experts,s.external_experts);assert.equal(d.performance.realized_pnl,0);assert.equal(d.external_experts[0].performance.realized_pnl,null);
 const legacy=await get(state());assert.deepEqual(legacy.external_experts,[]);
});

test('account-wide risk retains discrepancy and missing totals without contaminating strategy performance',async()=>{
 const s=state();s.account_risk={status:'CURRENT',complete:true,total_risk:null,exposures:[{kind:'PENDING',status:'SPEC_CONFLICT',broker_loss_to_sl:9090}]};
 const d=await get(s);const {portfolio,...original}=d.account_risk;assert.deepEqual(original,s.account_risk);assert.equal(portfolio.limits_enforced,false);assert.equal(d.performance.realized_pnl,0);
 assert.equal((await get(state())).account_risk.portfolio.status,'STALE_OR_INCOMPLETE');
});
test('open session with delayed quotes is distinguished from a closed session',async()=>{
 const s=state();s.sleeves[0].session_open=true;s.sleeves[0].feed_ok=false;s.sleeves[0].tick_age_seconds=900;
 const d=await get(s);const symbol=d.symbols.find(s=>s.symbol==='XAUUSD'&&s.timeframe==='H4');assert.equal(symbol.current_wait_reason,'QUOTE_NOT_FRESH');assert.equal(symbol.quote_age_seconds,900);
 s.sleeves[0].session_open=false;assert.equal((await get(s)).symbols.find(s=>s.symbol==='XAUUSD'&&s.timeframe==='H4').current_wait_reason,'SESSION_CLOSED');
});

test('additional research keeps unknown statistics and never becomes an execution sleeve',async()=>{
 const s=state();s.asset_research=[{symbol:'EURUSD',timeframe:'D1',status:'DESCRIPTIVE_ONLY',execution_enabled:false,momentum_20_pct:null,proposal:'WATCH'},{symbol:'NVDA',timeframe:'D1',status:'INSUFFICIENT_HISTORY',execution_enabled:false}];
 const d=await get(s);
 assert.deepEqual(d.asset_research,s.asset_research);
 assert.equal(d.asset_research[0].momentum_20_pct,null);
 assert.equal(d.symbols.length,5);
 assert.equal(d.symbols.some(row=>row.symbol==='EURUSD'||row.symbol==='NVDA'),false);
 assert.equal(d.performance.realized_pnl,0);
 s.asset_research={symbol:'EURUSD'};
 assert.deepEqual((await get(s)).asset_research,[]);
});

test('frequent modern capture becomes stale after three minutes despite a fresh database receipt',async()=>{
 const s=state();s.release_id='v5.4.6-demo-candidate';s.visibility={local_capture:true};s.observed_at=new Date(Date.now()-4*60000).toISOString();
 const d=await get(s);
 assert.equal(d.operational.status,'STALE');
 assert.equal(d.evidence.observation_max_age_seconds,180);
 assert.equal(d.evidence.analysis_current,false);
 assert.ok(d.symbols.every(row=>row.analysis_health==='STALE'));
 const legacy=state();legacy.observed_at=new Date(Date.now()-4*60000).toISOString();
 assert.equal((await get(legacy)).evidence.observation_max_age_seconds,2100);
});

test('future observation time and missing analysis do not invent liveness or a flat signal',async()=>{
 const s=state();s.observed_at=new Date(Date.now()+15*60000).toISOString();s.sleeves=[];
 const d=await get(s);
 assert.equal(d.operational.status,'STALE');
 assert.ok(d.symbols.every(row=>row.signal==='UNKNOWN'&&row.position==='UNKNOWN'));
 assert.deepEqual(d.asset_research,[]);
});
