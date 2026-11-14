// P1 observation only. Stop-loss budgets are not covariance contributions or guarantees.
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- Broker JSON fields are checked for type, completeness and freshness before valuation below.
type Row = Record<string, any>
const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n)
const currencies = new Set(['USD','EUR','JPY','GBP','CHF','CAD','AUD','NZD','CNH','CNY','SEK','NOK','MXN'])
const legs:Record<string,string[]>={USDJPY:['USD','JPY'],USDCHF:['USD','CHF'],EURUSD:['EUR','USD'],EURJPY:['EUR','JPY'],GBPUSD:['GBP','USD'],USDCAD:['USD','CAD'],AUDUSD:['AUD','USD']}
const baseOf=(row:Row)=>row.symbol_spec?.base_currency??legs[row.symbol]?.[0]
const quoteOf=(row:Row)=>row.symbol_spec?.profit_currency??legs[row.symbol]?.[1]
export function exposureFactors(row: Row): Array<{name:string;direction:number}> {
 const side=row.type===0 || [2,4,6].includes(row.type) ? 1 : row.type===1 || [3,5,7].includes(row.type) ? -1 : 0
 const base=baseOf(row), quote=quoteOf(row)
 if(!side) return [{name:'Sin clasificar',direction:0}]
 if(currencies.has(base) && currencies.has(quote) && base!==quote) return [{name:base,direction:side},{name:quote,direction:-side}]
 if(base==='XAU' || row.symbol==='XAUUSD') return [{name:'Oro',direction:side},...(currencies.has(quote)?[{name:quote,direction:-side}]:[])]
 // Explicit research universe, not a generic symbol-name parser.
 if(['AMD','NVDA'].includes(row.symbol)) return [{name:'Acciones EE. UU.',direction:side}]
 return [{name:'Sin clasificar',direction:0}]
}
export function buildPortfolioRisk(risk:Row|null, runtime:Row|null, nowMs:number, history:Row[]|null=null) {
 const rawRows:unknown[]=Array.isArray(risk?.exposures)?risk.exposures:[]
 const rows:Row[]=rawRows.filter((r):r is Row=>r!==null && typeof r==='object' && !Array.isArray(r))
 const age=risk?.observed_at ? (nowMs-Date.parse(risk.observed_at))/1000 : NaN
 const rootAge=runtime?.observed_at ? (nowMs-Date.parse(runtime.observed_at))/1000 : NaN
 const identity=!!runtime?.account_login && !!runtime?.account_server && !!runtime?.account_currency
 const fresh=identity && Number.isFinite(age) && age>=0 && age<=120 && Number.isFinite(rootAge) && rootAge>=0 && rootAge<=120 && runtime?.terminal_connected===true && runtime?.runtime_event!=='deinit'
 const counts=rows.filter(r=>r.kind==='POSITION').length===risk?.position_count && rows.filter(r=>r.kind==='PENDING').length===risk?.pending_count
 const unique=new Set(rows.map(r=>r.kind+':'+r.ticket)).size===rows.length
 const valued=rows.every(r=>['POSITION','PENDING'].includes(r.kind) && r.ticket!=null && r.status==='BROKER_CALCULATED' && finite(r.risk) && r.risk>=0)
 const currencyMatch=risk?.currency===runtime?.account_currency
 const valid=!!risk?.complete && fresh && counts && unique && valued && rows.length===rawRows.length && currencyMatch
 const capital=finite(runtime?.balance)&&finite(runtime?.equity)&&Math.min(runtime.balance,runtime.equity)>0 ? Math.min(runtime.balance,runtime.equity) : null
 const groups=new Map<string,{name:string;positions:number;pending:number;long:number;short:number;risk:number;unknown:number}>()
 for(const row of rows) for(const f of exposureFactors(row)) {
  const g=groups.get(f.name)??{name:f.name,positions:0,pending:0,long:0,short:0,risk:0,unknown:0}
  if(row.kind==='POSITION')g.positions++;else if(row.kind==='PENDING')g.pending++
  if(f.direction>0)g.long++;else if(f.direction<0)g.short++
  if(row.status==='BROKER_CALCULATED'&&finite(row.risk)&&row.risk>=0)g.risk+=row.risk;else g.unknown++
  groups.set(f.name,g)
 }
 const total=valid?rows.reduce((sum,r)=>sum+r.risk,0):null
 const gold=rows.filter(r=>exposureFactors(r).some(f=>f.name==='Oro'))
 const usdFx=rows.filter(r=>{return currencies.has(baseOf(r))&&currencies.has(quoteOf(r))&&[baseOf(r),quoteOf(r)].includes('USD')})
 const sum=(rs:Row[])=>valid?rs.reduce((s,r)=>s+r.risk,0):null
 const budget=(name:string,pct:number,used:number|null,classified=true)=>({name,pct,limit:capital===null?null:capital*pct/100,used:classified?used:null,
  remaining:classified&&capital!==null&&used!==null?Math.max(0,capital*pct/100-used):null,
  status:!classified||capital===null||used===null?'UNKNOWN':used>capital*pct/100?'EXCEEDED':'WITHIN_PROPOSED_LIMIT'})
 const classified=!groups.has('Sin clasificar')
 return {version:'portfolio-risk-p1',mode:'OBSERVE',execution_authority:'NONE',limits_enforced:false,
  observed_at:risk?.observed_at??null,status:valid?'VALIDATED_OBSERVATION':'STALE_OR_INCOMPLETE',capital_basis:capital,
  total_risk:total,open_risk:sum(rows.filter(r=>r.kind==='POSITION')),pending_risk:sum(rows.filter(r=>r.kind==='PENDING')),
  budgets:[budget('Toda la cuenta',2,total),budget('FX con USD',1,sum(usdFx),classified),budget('Oro',1,sum(gold),classified)],
  factors:[...groups.values()].map(g=>({...g,risk:valid&&g.unknown===0?g.risk:null})),
  factors_note:'Dirección por exposición; los riesgos por factor se superponen y no se suman. No representan sensibilidad monetaria neta ni contribuciones de covarianza.',
  diversification:{status:'INSUFFICIENT_DATA',common_daily_observations:0,required_daily_observations:252,allocation_enabled:false,
   reason:'Faltan series diarias sincronizadas de resultados por estrategia, valoradas a mercado y ajustadas por flujos. Los cierres aislados no sustituyen esas series.'},
  p0_gate:'PENDING_NATIVE_TESTS_AND_RESEARCH_RERUN',incidents:history,incident_status:history===null?'UNAVAILABLE':'AVAILABLE'}
}
export type PortfolioRiskReport = ReturnType<typeof buildPortfolioRisk>
