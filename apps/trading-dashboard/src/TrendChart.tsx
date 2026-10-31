import { useState } from 'react'
import type { PointerEvent } from 'react'
import './TrendChart.css'

type N = number | null
export type ChartSeries = {
  symbol: string; timeframe: string; status: string; execution_sleeve: boolean; ea_alignment?: string | null
  entry_lookback: N; exit_lookback: N; sma_period: N; atr_period: N
  source_file?: string; source_modified_at?: string; last_closed_bar?: string
  bars: (string | number | null)[][]
  ea_decision?: { bar_time?: string; target_position?: N; order_status?: string; order_message?: string; health?: string } | null
}
export type TrendData = { status?: string; observed_at?: string; as_of_broker?: string; release_id?: string; series?: ChartSeries[] }
type Candle = { time: string; open: number; high: number; low: number; close: number; ma: N; hi: N; lo: N; exitHi: N; exitLo: N; atr: N; signal: number; closed: boolean }
type Protection = { symbol?: string; timeframe?: string; sl?: N; tp?: N }
const number = (v: unknown): N => typeof v === 'number' && Number.isFinite(v) ? v : null
const stamp = (v?: string) => v ? v.replace('T', ' ').slice(0, 16) : 'Sin dato'
const stateLabels: Record<string, string> = { READY: 'Histórico disponible', WAIT_SESSION: 'Espera sesión y cotización', NO_ACTION: 'Sin orden nueva', OBSERVE: 'Observación', OPEN_OK: 'Apertura aceptada', RISK_BLOCKED: 'Bloqueo de riesgo', INSUFFICIENT_HISTORY: 'Histórico insuficiente', MISSING_EXPORT: 'Falta exportación de barras', SOURCE_REVIEW: 'Exportación por revisar', UNAVAILABLE: 'Gráficos temporalmente no disponibles', NOT_CONFIGURED: 'Esperando datos gráficos' }
const status = (s?: string) => s ? stateLabels[s] ?? s : 'Sin dato'
function decode(bars: ChartSeries['bars']): Candle[] {
  return bars.flatMap(b => {
    const [o, h, l, c] = b.slice(1, 5).map(number)
    if (typeof b[0] !== 'string' || o === null || h === null || l === null || c === null) return []
    return [{ time: b[0], open: o, high: h, low: l, close: c, ma: number(b[5]), hi: number(b[6]), lo: number(b[7]), exitHi: number(b[8]), exitLo: number(b[9]), atr: number(b[10]), signal: number(b[11]) ?? 0, closed: b[12] === 1 }]
  })
}

function Candles({ series, count, positions }: { series: ChartSeries; count: number; positions: Protection[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [trend, setTrend] = useState(true)
  const [entry, setEntry] = useState(true)
  const [exit, setExit] = useState(false)
  const candles = decode(series.bars).slice(-count)
  const width = 1100, height = 420, left = 18, right = 88, top = 29, bottom = 38
  const w = width - left - right, h = height - top - bottom
  const precision = series.symbol === 'USDCHF' ? 5 : series.symbol === 'USDJPY' ? 3 : 2
  const price = (v: N | undefined) => v == null ? 'Sin dato' : v.toLocaleString('es-MX', { minimumFractionDigits: precision, maximumFractionDigits: precision })
  const own = positions.find(p => p.symbol === series.symbol && p.timeframe === series.timeframe)
  const values = candles.flatMap(c => [c.low, c.high, ...(trend && c.ma != null ? [c.ma] : []), ...(entry ? [c.hi, c.lo] : []), ...(exit ? [c.exitHi, c.exitLo] : [])]).filter((n): n is number => n !== null)
  if (own?.sl) values.push(own.sl)
  if (own?.tp) values.push(own.tp)
  if (!candles.length || !values.length) return <div className="chart-empty">{status(series.status)}. Se necesita el CSV del broker para esta combinación; no se dibujan precios estimados.</div>
  const min = Math.min(...values), max = Math.max(...values), pad = Math.max((max - min) * .07, max * .0001)
  const lower = min - pad, upper = max + pad
  const y = (v: number) => top + (upper - v) / (upper - lower) * h
  const step = w / candles.length, x = (i: number) => left + (i + .5) * step
  const latestClosed = candles.findLastIndex(c => c.closed)
  const index = Math.max(0, Math.min(hover ?? (latestClosed >= 0 ? latestClosed : candles.length - 1), candles.length - 1))
  const current = candles[index]
  const path = (key: 'ma' | 'hi' | 'lo' | 'exitHi' | 'exitLo') => {
    let gap = true
    return candles.map((c, i) => {
      const value = c[key]
      if (value === null) { gap = true; return '' }
      const next = `${gap ? 'M' : 'L'}${x(i).toFixed(2)},${y(value).toFixed(2)}`
      gap = false
      return next
    }).join(' ')
  }
  const areaBars = candles.map((c, i) => ({ c, i })).filter(({ c }) => c.hi !== null && c.lo !== null)
  const area = areaBars.map(({ c, i }) => `${x(i)},${y(c.hi!)}`).concat(areaBars.toReversed().map(({ c, i }) => `${x(i)},${y(c.lo!)}`)).join(' ')
  const move = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect()
    setHover(Math.max(0, Math.min(candles.length - 1, Math.floor(((e.clientX - box.left) / box.width * width - left) / step))))
  }
  const technical = !current.closed ? 'Vela sin cierre confirmado' : current.signal === 1 ? 'Ruptura BUY confirmada al cierre' : current.signal === -1 ? 'Ruptura SELL confirmada al cierre' : current.hi != null && current.close > current.hi || current.lo != null && current.close < current.lo ? 'Ruptura de canal · filtro SMA no cumplido' : current.hi != null && current.high > current.hi || current.lo != null && current.low < current.lo ? 'Cruce por mecha · sin ruptura por cierre' : 'Sin ruptura de entrada'
  const trendLabel = current.ma == null ? 'Sin SMA suficiente' : current.close > current.ma ? 'Alcista: cierre sobre SMA' : current.close < current.ma ? 'Bajista: cierre bajo SMA' : 'Cierre igual a SMA'
  const triggers = candles.filter(c => c.closed && c.signal !== 0)
  return <>
    <div className="chart-overlays" aria-label="Capas del gráfico">
      <label><input type="checkbox" checked={trend} onChange={e => setTrend(e.target.checked)} /><i className="legend-ma" />SMA {series.sma_period}</label>
      <label><input type="checkbox" checked={entry} onChange={e => setEntry(e.target.checked)} /><i className="legend-entry" />Canal de entrada {series.entry_lookback}</label>
      <label><input type="checkbox" checked={exit} onChange={e => setExit(e.target.checked)} /><i className="legend-exit" />Canal de salida {series.exit_lookback}</label>
      <span><b className="chart-buy">▲</b> BUY <b className="chart-sell">▼</b> SELL · condición técnica al cierre</span>
    </div>
    <div className="chart-canvas">
      <svg viewBox={`0 0 ${width} ${height}`} aria-label={`Velas de ${series.symbol} ${series.timeframe}, SMA y canales Donchian`} role="img">
        <defs><clipPath id="trend-plot-clip"><rect x={left} y={top - 18} width={w} height={h + 30} /></clipPath></defs>
        {Array.from({ length: 6 }, (_, i) => {
          const p = lower + (upper - lower) * i / 5
          return <g key={i}><line className="chart-grid-line" x1={left} x2={left + w} y1={y(p)} y2={y(p)} /><text className="chart-axis" x={left + w + 12} y={y(p) + 4}>{price(p)}</text></g>
        })}
        <g clipPath="url(#trend-plot-clip)">
          {entry && area && <polygon points={area} className="chart-channel-area" />}
          {entry && <><path d={path('hi')} className="chart-entry-line" /><path d={path('lo')} className="chart-entry-line" /></>}
          {exit && <><path d={path('exitHi')} className="chart-exit-line" /><path d={path('exitLo')} className="chart-exit-line" /></>}
          {candles.map((c, i) => <g key={c.time} className={`${c.close >= c.open ? 'candle-up' : 'candle-down'} ${!c.closed ? 'candle-unconfirmed' : ''}`}>
            <line x1={x(i)} x2={x(i)} y1={y(c.high)} y2={y(c.low)} />
            <rect x={x(i) - Math.min(step * .62, 12) / 2} width={Math.min(step * .62, 12)} y={Math.min(y(c.open), y(c.close))} height={Math.max(1.2, Math.abs(y(c.open) - y(c.close)))} />
            {c.closed && c.signal === 1 && <path className="chart-signal-buy" d={`M${x(i)},${y(c.low) + 7}l-4,7h8z`} />}
            {c.closed && c.signal === -1 && <path className="chart-signal-sell" d={`M${x(i)},${y(c.high) - 7}l-4,-7h8z`} />}
          </g>)}
          {trend && <path d={path('ma')} className="chart-ma-line" />}
          {own && (['sl', 'tp'] as const).map(key => own[key] ? <g key={key}><line x1={left} x2={left + w} y1={y(own[key]!)} y2={y(own[key]!)} className={`chart-${key}-line`} /><text x={left + 7} y={y(own[key]!) - 5} className="chart-protection-label">{key.toUpperCase()} broker {price(own[key])}</text></g> : null)}
          <line className="chart-crosshair" x1={x(index)} x2={x(index)} y1={top} y2={top + h} />
          <line className="chart-crosshair" x1={left} x2={left + w} y1={y(current.close)} y2={y(current.close)} />
          <circle cx={x(index)} cy={y(current.close)} r="3.5" className="chart-cross-point" />
        </g>
        {Array.from(new Set([0, Math.floor(candles.length * .25), Math.floor(candles.length * .5), Math.floor(candles.length * .75), candles.length - 1])).map(i => <text key={i} className="chart-axis" x={x(i)} y={height - 10} textAnchor={i === 0 ? 'start' : i === candles.length - 1 ? 'end' : 'middle'}>{candles[i].time.slice(5, 10)}{series.timeframe === 'H4' ? ` ${candles[i].time.slice(11, 16)}` : ''}</text>)}
        <rect x={left} y={top} width={w} height={h} fill="transparent" tabIndex={0} role="slider" aria-label="Recorrer velas con flechas izquierda y derecha" aria-valuemin={0} aria-valuemax={candles.length - 1} aria-valuenow={index} aria-valuetext={`${stamp(current.time)} cierre ${price(current.close)}`} onPointerMove={move} onPointerLeave={() => setHover(null)} onKeyDown={e => {
          if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setHover(Math.max(0, Math.min(candles.length - 1, index + (e.key === 'ArrowLeft' ? -1 : 1)))) }
          if (e.key === 'Escape') setHover(null)
        }} />
      </svg>
    </div>
    <div className="chart-candle-detail"><strong>{stamp(current.time)} <small>reloj broker · {current.closed ? 'cerrada por barra sucesora' : 'cierre sin confirmar'}</small></strong><span>A {price(current.open)}</span><span>Máx {price(current.high)}</span><span>Mín {price(current.low)}</span><span>C {price(current.close)}</span></div>
    <div className="chart-readout">
      <div><span>Tendencia de esta vela</span><strong>{trendLabel}</strong><p>SMA {series.sma_period}: {price(current.ma)}</p></div>
      <div><span>Ruptura calculada</span><strong className={current.signal > 0 ? 'chart-buy' : current.signal < 0 ? 'chart-sell' : ''}>{technical}</strong><p>Entrada {price(current.lo)} — {price(current.hi)} · ATR {series.atr_period}: {price(current.atr)}</p></div>
      <div><span>Decisión registrada del expert</span><strong>{series.execution_sleeve ? status(series.ea_decision?.order_status) : 'Comparación fuera de manga activa'}</strong><p>{series.execution_sleeve ? `${stamp(series.ea_decision?.bar_time)} · objetivo ${series.ea_decision?.target_position === 1 ? 'BUY' : series.ea_decision?.target_position === -1 ? 'SELL' : series.ea_decision?.target_position === 0 ? 'FLAT' : 'sin dato'}` : 'Esta combinación no habilita operaciones.'}</p></div>
    </div>
    <p className="chart-caption">Canales excluyen la vela de decisión; la SMA incluye su cierre. Una ruptura marcada es una condición histórica estando plano: puede mantener una posición existente y no acredita una orden ejecutada. La última vela sin sucesora se dibuja atenuada y no genera señal. SL/TP broker sólo se superponen si la posición está atribuida a esta manga.</p>
    <details className="chart-signals"><summary>Rupturas técnicas en el rango visible ({triggers.length})</summary>{triggers.length ? <div className="chart-signal-table"><table><thead><tr><th>Vela · broker</th><th>Condición</th><th>Cierre</th><th>Nivel superado</th></tr></thead><tbody>{triggers.toReversed().map(c => <tr key={c.time}><td>{stamp(c.time)}</td><td className={c.signal > 0 ? 'chart-buy' : 'chart-sell'}>{c.signal > 0 ? 'BUY' : 'SELL'}</td><td>{price(c.close)}</td><td>{price(c.signal > 0 ? c.hi : c.lo)}</td></tr>)}</tbody></table></div> : <p className="quiet">Sin rupturas confirmadas en estas velas.</p>}</details>
  </>
}

export default function TrendChart({ data, positions = [] }: { data?: TrendData | null; positions?: Protection[] }) {
  const [symbol, setSymbol] = useState('XAUUSD')
  const [timeframe, setTimeframe] = useState('H4')
  const [count, setCount] = useState(80)
  const series = data?.series ?? []
  const selected = series.find(s => s.symbol === symbol && s.timeframe === timeframe)
  return <section id="trend-analysis" className="panel trend-panel" aria-labelledby="trend-title">
    <div className="section-top"><div><p className="eyebrow">Precio y reglas del expert</p><h2 id="trend-title">Tendencias y rupturas</h2></div><span className={`chart-scope ${selected?.execution_sleeve ? 'chart-scope-active' : ''}`}>{selected?.execution_sleeve ? 'Manga activa de PortfolioTrend' : 'Comparación exploratoria'}</span></div>
    <p className="section-copy">Explora el canal que debe superar el cierre y su relación con la tendencia. Desplaza el cursor o usa las flechas sobre el gráfico para examinar una vela.</p>
    <div className="chart-filters">
      <label>Activo<select value={symbol} onChange={e => setSymbol(e.target.value)}>{['USDJPY', 'USDCHF', 'XAUUSD', 'AMD'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label>Temporalidad<select value={timeframe} onChange={e => setTimeframe(e.target.value)}><option value="H4">H4 · 4 horas</option><option value="D1">D1 · diaria</option></select></label>
      <label>Rango visible<select value={count} onChange={e => setCount(Number(e.target.value))}>{[40, 80, 160].map(n => <option key={n} value={n}>{n} velas</option>)}</select></label>
      <div className="chart-rule">{selected ? <><strong>Donchian {selected.entry_lookback}/{selected.exit_lookback} · SMA {selected.sma_period}</strong><span>{symbol} / {timeframe} · {status(selected.status)}</span></> : <span>{status(data?.status)}</span>}</div>
    </div>
    {selected?.execution_sleeve && selected.ea_alignment && selected.ea_alignment !== 'MATCHED' && <p className="notice">{selected.ea_alignment === 'FEATURE_MISMATCH' ? 'Los niveles reconstruidos difieren del registro del expert; revisar la fuente antes de evaluar esta entrada.' : 'La exportación todavía no permite conciliar la última vela del expert. Se conserva el histórico disponible.'}</p>}
    {selected ? <Candles key={`${symbol}-${timeframe}-${count}`} series={selected} count={count} positions={positions} /> : <div className="chart-empty">Esperando histórico del broker para los gráficos. El estado operativo del expert se consulta por separado.</div>}
    <div className="panel-foot"><span>Datos: {selected?.source_file ?? 'sin exportación'} · tiempo de barras en reloj del broker</span><span>Última vela cerrada disponible: {stamp(selected?.last_closed_bar)}</span><span>Reconstrucción visual · no modifica órdenes ni parámetros</span></div>
  </section>
}
