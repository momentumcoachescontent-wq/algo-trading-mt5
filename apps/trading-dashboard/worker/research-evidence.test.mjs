import test from 'node:test'
import assert from 'node:assert/strict'
import { publicResearchEvidence } from './research-evidence.ts'
const now=Date.parse('2026-10-27T15:00:00Z')
const sample=()=>({schema_version:1,status:'INSUFFICIENT_EXECUTION_SAMPLE',as_of_utc:'2026-10-27T14:00:00Z',generated_at_utc:'2026-10-27T14:05:00Z',decision_count:12,entry_candidate_count:1,linked_closed_trades:0,feature_coverage:{atr:{known:0,total:12}},execution_authority:'SEND_ORDERS',profitability_validated:true,account_login:'private',raw_decisions:[{secret:'private'}]})
test('research evidence is allowlisted and never gains execution authority or validated profitability',()=>{
 const row=publicResearchEvidence(sample(),now)
 assert.equal(row.execution_authority,'NONE');assert.equal(row.profitability_validated,false)
 assert.equal(row.linked_closed_trades,0);assert.equal(row.feature_coverage.atr.known,0)
 assert.equal(row.account_login,undefined);assert.equal(row.raw_decisions,undefined)
 assert.equal(row.refresh_mode,'ON_DEMAND_DATASET')
})
test('a fresh dashboard query does not refresh an old or future research artifact',()=>{
 const s=sample();s.as_of_utc='2026-10-25T13:00:00Z';s.generated_at_utc='2026-10-25T14:00:00Z';assert.equal(publicResearchEvidence(s,now).freshness,'STALE_RESEARCH')
 s.generated_at_utc='2026-10-28T14:00:00Z';assert.equal(publicResearchEvidence(s,now).freshness,'UNVERIFIED')
 s.generated_at_utc='2026-10-27T14:00:00';assert.equal(publicResearchEvidence(s,now).freshness,'UNVERIFIED')
 s.generated_at_utc='2026-10-27T14:00:00Z';s.as_of_utc='2026-10-28T14:00:00Z';assert.equal(publicResearchEvidence(s,now).freshness,'UNVERIFIED')
 s.as_of_utc='2026-10-27T14:10:00Z';assert.equal(publicResearchEvidence(s,now).freshness,'UNVERIFIED')
})
test('missing and invalid coverage stays unknown, never inventing a complete sample',()=>{
 assert.equal(publicResearchEvidence(null,now),null);assert.equal(publicResearchEvidence({schema_version:2},now),null)
 const s=sample();s.linked_closed_trades=-1;s.decision_count='12';s.feature_coverage.atr={known:13,total:12}
 const row=publicResearchEvidence(s,now);assert.equal(row.linked_closed_trades,null);assert.equal(row.decision_count,null);assert.equal(row.feature_coverage.atr.known,null)
})
