import test from 'node:test'
import assert from 'node:assert/strict'
import {buildPortfolioRisk,exposureFactors} from './portfolio-risk.ts'
const now=Date.parse('2026-10-10T12:00:00Z')
const runtime={account_login:1,account_server:'Demo',account_currency:'USD',balance:10000,equity:9000,observed_at:new Date(now).toISOString(),terminal_connected:true}
const row={kind:'PENDING',ticket:'1',type:4,symbol:'USDJPY',risk:100,status:'BROKER_CALCULATED',symbol_spec:{profit_currency:'JPY'}}
const risk={complete:true,currency:'USD',observed_at:runtime.observed_at,position_count:0,pending_count:1,exposures:[row]}
test('whole-account risk includes pending and uses lower capital',()=>{
 const r=buildPortfolioRisk(risk,runtime,now,[])
 assert.equal(r.total_risk,100);assert.equal(r.budgets[0].limit,180);assert.equal(r.budgets[1].status,'EXCEEDED')
 assert.equal(r.limits_enforced,false);assert.equal(r.diversification.allocation_enabled,false)
 assert.deepEqual(exposureFactors(row),[{name:'USD',direction:1},{name:'JPY',direction:-1}])
})
test('opposed positions never net stop-loss risk or factor budgets',()=>{
 const r=buildPortfolioRisk({...risk,pending_count:2,exposures:[row,{...row,type:5,ticket:'2'}]},runtime,now)
 assert.equal(r.total_risk,200);assert.equal(r.factors.find(x=>x.name==='USD').risk,200)
})
test('stale future incomplete duplicate and invalid valuations are unknown',()=>{
 for(const r of [{...risk,observed_at:new Date(now-121000).toISOString()},{...risk,observed_at:new Date(now+1000).toISOString()},{...risk,complete:false},{...risk,pending_count:2,exposures:[row,row]},{...risk,exposures:[{...row,status:'SPEC_CONFLICT'}]}])assert.equal(buildPortfolioRisk(r,runtime,now).total_risk,null)
 assert.equal(buildPortfolioRisk(risk,{...runtime,runtime_event:'deinit'},now).total_risk,null)
})
test('unknown factors never claim an unused gold or FX budget',()=>{
 const r=buildPortfolioRisk({...risk,exposures:[{...row,symbol:'ALIAS',symbol_spec:{}}]},runtime,now)
 assert.equal(r.budgets[1].used,null);assert.equal(r.budgets[2].used,null)
 assert.equal(r.incidents,null)
})
