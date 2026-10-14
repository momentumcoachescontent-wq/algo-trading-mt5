import { useEffect, useMemo, useState } from 'react'
import './ObservabilityPanel.css'

type Asset = { symbol: string; version: string; timeframe: string; strategy: string; last_seen: string }
type Evaluation = {
  at: string; decision: string; reason: string | null; timeframe: string; close: number | null
  ema: number | null; sma: number | null; channel_high: number | null; channel_low: number | null
  atr: number | null; order_status: string | null; ea_version: string
}
type Trade = { position_id: number | string | null; symbol: string; event_type: string; direction: string
  open_time: string | null; close_time: string | null; pnl: number | null; excluded: boolean; ea_version: string }
type Candle = { time: string; open: number; high: number; low: number; close: number; volume: number | null }
type Overview = {
  evaluations: number; blocked: number; entry_ready: number; last_decision: string | null
  errors: number; closed_trades: number; realized_pnl: number; win_rate: number | null
  last_evaluation: string | null; evaluation_age_minutes: number | null
  last_lifecycle_event: string | null; recent_lifecycle_events: number; distinct_boot_ids: number
  blocked_reasons: { reason: string; count: number }[]
  economic_scope: string; sample: { limited: boolean }
}
type State<T> = { data: T | null; error: string | null; loading: boolean }
const empty = <T,>(): State<T> => ({ data: null, error: null, loading: true })
const stamp = (t: string | null | undefined) =>
  t ? new Intl.DateTimeFormat('es-MX', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Mexico_City' }).format(new Date(t)) : 'Sin datos'
const fmt = (n: number | null | undefined, digits = 2) =>
  n == null || !Number.isFinite(n) ? '—' : n.toLocaleString('es-MX', { maximumFractionDigits: digits })
const number = (n: unknown) => typeof n === 'number' && Number.isFinite(n) ? n : null
function useEndpoint<T>(url: string, refreshMs = 60_000): State<T> {
  const [state, setState] = useState<State<T>>(empty<T>)
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    async function load() {
      try {
        const result = await fetch(url, { signal: controller.signal, cache: 'no-store' })
        const data = await result.json() as T & { ok?: boolean; error?: string }
        if (!result.ok || data.ok === false) throw Error(data.error || 'Error HTTP ' + result.status)
        if (active) setState({ data, error: null, loading: false })
      } catch (err) {
        if (active && !(err instanceof Error && err.name === 'AbortError'))
          setState(prev => ({ ...prev, error: err instanceof Error ? err.message : String(err), loading: false }))
      }
    }
    setState(empty<T>())
    void load()
    const timer = window.setInterval(() => { void load() }, refreshMs)
    return () => { active = false; window.clearInterval(timer); controller.abort() }
  }, [url, refreshMs])
  return state
}
function MovingAverage({ candles, period, color, view, width, exponential }: {
  candles: Candle[]; period: number; color: string
  view: (v: number) => number; width: number; exponential: boolean
}) {
  const values: string[] = []
  if (candles.length < period) return null
  let rolling = 0
  let average = 0
  const k = 2 / (period + 1)
  for (let i = 0; i < candles.length; i++) {
    rolling += candles[i].close
    if (i >= period) rolling -= candles[i - period].close
    if (i === period - 1) average = rolling / period
    else if (i >= period) average = exponential ? candles[i].close * k + average * (1 - k) : rolling / period
    if (i >= period - 1) {
      const x = (i + .5) * width / candles.length
      values.push(x.toFixed(1) + ',' + view(average).toFixed(1))
    }
  }
  return <polyline points={values.join(' ')} fill="none" stroke={color} strokeWidth="2"
    strokeLinejoin="round" opacity=".9" />
}
function CandleChart({ candles, evaluations, version }: { candles: Candle[]; evaluations: Evaluation[]; version: string }) {
  const [hovered, setHovered] = useState<number | null>(null)
  const bars = useMemo(() => candles.slice(-260).filter(c =>
    [c.open, c.high, c.low, c.close].every(v => Number.isFinite(v))), [candles])
  if (bars.length === 0) return (
    <div className="obs-empty">
      No hay velas OHLC importadas para este activo y temporalidad.
      <small>Las evaluaciones y operaciones siguen disponibles; las velas requieren una exportación pasiva de MT5.</small>
    </div>
  )
  const width = 900, height = 295, top = 14, bottom = 278
  const lo = Math.min(...bars.map(x => x.low)), hi = Math.max(...bars.map(x => x.high))
  const padding = Math.max((hi - lo) * .07, .000001)
  const low = lo - padding, high = hi + padding
  const y = (price: number) => top + (high - price) / (high - low) * (bottom - top)
  const step = width / bars.length
  const body = Math.max(1.3, Math.min(step * .65, 9))
  const selected = hovered == null ? bars[bars.length - 1] : bars[hovered]
  const markers = new Map<number, string>()
  for (const e of evaluations) {
    const t = Date.parse(e.at)
    if (!Number.isFinite(t)) continue
    const i = bars.findLastIndex((b, ix) => Date.parse(b.time) <= t &&
      (ix === bars.length - 1 || Date.parse(bars[ix + 1].time) > t))
    if (i >= 0) markers.set(i, e.decision)
  }
  const averagePeriod = version.startsWith('v5') ? 200 : 21
  return <div className="obs-chart">
    <div className="obs-chart-legend">
      <span>OHLC MT5</span>
      <strong>{stamp(selected.time)}</strong>
      <span>O {fmt(selected.open, 5)} · H {fmt(selected.high, 5)} · L {fmt(selected.low, 5)} · C {fmt(selected.close, 5)}</span>
    </div>
    <svg viewBox="0 0 900 295" role="img" aria-label="Gráfico de velas históricas de MT5 con marcadores observacionales">
      {Array.from({ length: 5 }, (_, i) => {
        const lineY = top + i * (bottom - top) / 4
        return <g key={i}><line x1={0} x2={width} y1={lineY} y2={lineY} stroke="#dbe3ed"/>
          <text x={width - 5} y={lineY - 4} fill="#64748b" fontSize="11" textAnchor="end">
            {fmt(high - i * (high - low) / 4, 5)}
          </text></g>
      })}
      {bars.map((bar, i) => {
        const x = (i + .5) * step
        const up = bar.close >= bar.open
        const paint = up ? '#059669' : '#e11d48'
        return <g key={bar.time}>
          <line x1={x} x2={x} y1={y(bar.high)} y2={y(bar.low)} stroke={paint} strokeWidth="1.3"/>
          <rect x={x - body / 2} y={Math.min(y(bar.open), y(bar.close))} width={body}
            height={Math.max(1.6, Math.abs(y(bar.open) - y(bar.close)))} fill={paint}/>
          <rect x={x - step / 2} y={0} width={step} height={height} fill="transparent"
            onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}>
            <title>{stamp(bar.time)} O {bar.open} H {bar.high} L {bar.low} C {bar.close}</title>
          </rect>
        </g>
      })}
      <MovingAverage candles={bars} period={averagePeriod} color="#d97706" width={width} view={y} exponential={!version.startsWith('v5')}/>
      {[...markers.entries()].map(([i, label]) =>
        <g key={i}><circle cx={(i + .5) * step} cy={Math.max(10, y(bars[i].high) - 10)}
          r="5" fill={label === 'BLOCKED' ? '#d97706' : '#2563eb'} stroke="white" strokeWidth="2">
          <title>{label}</title></circle></g>
      )}
    </svg>
    <div className="obs-chart-note">
      {version.startsWith('v5') ? 'SMA200 orientativa calculada de las velas disponibles' : 'EMA21 de referencia calculada con las velas disponibles'} ·
      Los círculos identifican evaluaciones cuando hay coincidencia temporal · No se generan señales
    </div>
  </div>
}
export default function ObservabilityPanel() {
  const assets = useEndpoint<{ assets: Asset[]; scope: string }>('/api/observability/assets', 5 * 60_000)
  const [symbol, setSymbol] = useState('USDJPY')
  const [version, setVersion] = useState('ALL')
  const [tf, setTf] = useState('H4')
  const options = useMemo(() => assets.data?.assets ?? [], [assets.data])
  const symbols = useMemo(() => [...new Set(options.map(a => a.symbol))].sort(), [options])
  const versions = useMemo(() => [...new Set(options.filter(a => a.symbol === symbol).map(a => a.version))].sort().reverse(), [options, symbol])
  const qs = new URLSearchParams({ symbol, timeframe: tf, limit: '300' })
  if (version !== 'ALL') qs.set('version', version)
  const overview = useEndpoint<Overview>('/api/observability/summary?' + qs.toString())
  const history = useEndpoint<{ evaluations: Evaluation[]; trades: Trade[]; scope: { sampled: boolean } }>(
    '/api/observability/timeline?' + qs.toString())
  const candles = useEndpoint<{ rows: Candle[]; last_candle: string | null }>(
    '/api/observability/candles?' + new URLSearchParams({ symbol, timeframe: tf, limit: '1000' }))
  const data = overview.data
  return <section className="obs-root" aria-label="Expert Observability">
    <div className="obs-heading"><div>
      <p className="eyebrow">Visualización multi-activo · Solo lectura</p>
      <h2>Expert Observability Terminal</h2>
      <p>Seguimiento histórico de las evaluaciones de MT5; esta pantalla no puede enviar ni modificar operaciones.</p>
    </div><span className="obs-readonly">READ ONLY</span></div>
    <div className="obs-controls">
      <label>Activo <select value={symbol} onChange={e => { setSymbol(e.target.value); setVersion('ALL') }}>
        {!symbols.includes(symbol) && <option value={symbol}>{symbol}</option>}
        {symbols.map(x => <option value={x} key={x}>{x}</option>)}</select></label>
      <label>Versión del Expert <select value={version} onChange={e => setVersion(e.target.value)}>
        <option value="ALL">Todas las versiones</option>
        {versions.map(v => <option value={v} key={v}>{v}</option>)}</select></label>
      <label>Temporalidad <select value={tf} onChange={e => setTf(e.target.value)}>
        <option value="H4">H4</option><option value="D1">D1</option></select></label>
      <div className="obs-freshness">Última evaluación: <strong>{stamp(data?.last_evaluation)}</strong>
        {data?.evaluation_age_minutes != null && <span> · hace {fmt(data.evaluation_age_minutes, 0)} min</span>}</div>
    </div>
    {assets.error && <p className="obs-warning">Activos: {assets.error}</p>}
    {overview.error && <p className="obs-warning">Resumen: {overview.error}</p>}
    {history.error && <p className="obs-warning">Evaluaciones: {history.error}</p>}
    {candles.error && <p className="obs-warning">Velas: {candles.error}</p>}
    {data?.sample.limited && <p className="obs-warning">Resultados calculados sobre muestra limitada; no representan todo el histórico.</p>}
    <div className="obs-kpis">
      {[
        ['Evaluaciones únicas', data?.evaluations],
        ['Bloqueadas', data?.blocked],
        ['ENTRY_READY', data?.entry_ready],
        ['Errores', data?.errors],
        ['Trades cerrados', data?.closed_trades],
        ['PNL cerrado (muestra)', data ? fmt(data.realized_pnl) : '—'],
      ].map(([label, value]) => <article className="obs-kpi" key={String(label)}>
        <span>{label}</span><strong>{value ?? '—'}</strong></article>)}
    </div>
    <div className="obs-layout">
      <div className="obs-graphbox">
        <div className="obs-section-heading"><h3>Precio y evaluación del Expert</h3>
          <span>Última vela: {stamp(candles.data?.last_candle)}</span></div>
        <CandleChart candles={candles.data?.rows ?? []} evaluations={history.data?.evaluations ?? []} version={version === 'ALL' ? versions[0] ?? 'ALL' : version}/>
      </div>
      <div className="obs-graphbox">
        <div className="obs-section-heading"><h3>Razones de bloqueo</h3><span>Frecuencia en muestra</span></div>
        {(data?.blocked_reasons ?? []).length === 0 ? <p className="obs-muted">Sin bloqueos en la muestra.</p> :
          data?.blocked_reasons.map(row => <div className="obs-reason" key={row.reason}>
            <span title={row.reason}>{row.reason}</span>
            <div><i style={{ width: String(100 * row.count / Math.max(1, data.blocked)) + '%' }}/></div>
            <strong>{row.count}</strong>
          </div>)}
        <div className="obs-lifecycle"><h4>Salud de telemetría</h4>
          <p>Último evento de ciclo de vida: {stamp(data?.last_lifecycle_event)}</p>
          <p>Eventos de ciclo de vida en la muestra: {data?.recent_lifecycle_events ?? '—'} · Boots distintos: {data?.distinct_boot_ids ?? '—'}</p>
          <small>Un evento ea_init no demuestra conectividad activa ni evaluación reciente.</small>
        </div>
      </div>
    </div>
    <div className="obs-graphbox">
      <div className="obs-section-heading"><h3>Últimas evaluaciones</h3>
        <span>{history.loading ? 'Actualizando…' : 'Histórico observacional'}</span></div>
      <div className="obs-table-scroll"><table><thead><tr>
        <th>Fecha CDMX</th><th>Versión</th><th>Estado</th><th>Motivo</th><th>Cierre reportado</th>
      </tr></thead><tbody>
        {(history.data?.evaluations ?? []).slice(0, 35).map((e, i) => <tr key={e.at + e.ea_version + i}>
          <td>{stamp(e.at)}</td><td>{e.ea_version}</td><td><b className={e.decision === 'BLOCKED' ? 'obs-blocked' : 'obs-ready'}>{e.decision}</b></td>
          <td>{e.reason ?? '—'}</td><td>{fmt(number(e.close), 5)}</td></tr>)}
        {!history.data?.evaluations.length && <tr><td colSpan={5}>Sin evaluaciones para los filtros seleccionados.</td></tr>}
      </tbody></table></div>
    </div>
    <div className="obs-graphbox">
      <div className="obs-section-heading"><h3>Operaciones registradas</h3>
        <span>Solo lectura · muestras de trades</span></div>
      <div className="obs-table-scroll"><table><thead><tr>
        <th>Fecha CDMX</th><th>Activo</th><th>Versión</th><th>Dirección</th>
        <th>Evento</th><th>PNL</th><th>Clasificación</th>
      </tr></thead><tbody>
        {(history.data?.trades ?? []).slice(0, 35).map((trade, i) => <tr key={String(trade.position_id) + trade.event_type + i}>
          <td>{stamp(trade.close_time ?? trade.open_time)}</td>
          <td>{trade.symbol}</td><td>{trade.ea_version}</td>
          <td>{trade.direction ?? '—'}</td>
          <td>{trade.event_type ?? '—'}</td>
          <td>{trade.close_time || trade.event_type === 'close' ? fmt(number(trade.pnl)) : 'Abierto'}</td>
          <td>{trade.excluded ? 'Excluido de edge' : 'Registrado'}</td>
        </tr>)}
        {!history.data?.trades.length && <tr><td colSpan={7}>Sin operaciones registradas para estos filtros.</td></tr>}
      </tbody></table></div>
    </div>
    <div className="obs-disclaimer">Datos observacionales de Supabase / MT5. Velas importadas de exportaciones MT5.
      Las métricas de operaciones pueden ser parciales; no representan señales de inversión, ni son parámetros de ejecución.</div>
  </section>
}
