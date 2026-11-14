import test from 'node:test'
import assert from 'node:assert/strict'
import { publicTrendCharts } from './trend-charts.ts'

const candle=(time,closed=1)=>[time,100,113,98,111,105,110,90,108,92,3,1,closed]
const fixture=(bars)=>({schema_version:1,as_of_broker:'2026-10-30T20:00:00',secret:'private',series:[{
  symbol:'XAUUSD',timeframe:'H4',status:'READY',execution_sleeve:true,secret:'private',
  bars,ea_decision:{bar_time:'2026-10-30T12:00:00',target_position:1,secret:'private'},
}]})

test('forming candles never become confirmed entry markers; arbitrary producer signal is recomputed',()=>{
  const output=publicTrendCharts(fixture([candle('2026-10-30T12:00:00'),candle('2026-10-30T16:00:00',0)]))
  assert.equal(output.series[0].bars[0][11],1)
  assert.equal(output.series[0].bars[1][11],0)
  const blocked=candle('2026-10-30T12:00:00');blocked[5]=120
  assert.equal(publicTrendCharts(fixture([blocked])).series[0].bars[0][11],0)
  assert.equal(output.secret,undefined);assert.equal(output.series[0].secret,undefined)
  assert.equal(output.series[0].ea_decision.secret,undefined)
})

test('future, invalid, repeated or unordered bars are not drawn as valid history',()=>{
  const invalid=candle('2026-10-30T16:00:00');invalid[2]=90
  const result=publicTrendCharts(fixture([candle('2026-10-30T12:00:00'),candle('2026-10-30T12:00:00'),
    candle('2026-10-30T08:00:00'),invalid,candle('2026-10-31T00:00:00')]))
  assert.equal(result.series[0].bars.length,1)
  assert.equal(publicTrendCharts(null),null)
  assert.equal(publicTrendCharts({schema_version:2}),null)
})

test('chart transport bounds points and assets and excludes unknown symbols',()=>{
  const raw=fixture([])
  raw.series=Array.from({length:20},()=>({...raw.series[0],bars:Array.from({length:200},(_,i)=>
    candle(`2026-10-${String(1+Math.floor(i/24)).padStart(2,'0')}T${String(i%24).padStart(2,'0')}:00:00`))}))
  assert.equal(publicTrendCharts(raw).series.length,8)
  assert.equal(publicTrendCharts(raw).series[0].bars.length,160)
  raw.series[0].symbol='private-account';assert.equal(publicTrendCharts(raw).series.length,7)
})
