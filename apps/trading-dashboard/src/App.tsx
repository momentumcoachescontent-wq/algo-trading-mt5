import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import './App.css'

type N = number | null
type Position = { symbol?: string; direction?: string; type?: number; lots?: N; volume?: N; price?: N; sl?: N; tp?: N; pnl?: N }
type External = {
  id?: string; status?: string; observed_at?: string | null; open_positions?: N
  pending_orders?: Position[] | null; positions?: Position[]; floating_pnl?: N
  history_complete?: boolean; issues?: string[]
}
type Sleeve = {
  symbol: string; timeframe: string; experimental?: boolean; analysis_health?: string
  order_status?: string; order_message?: string | null; current_wait_reason?: string | null
  signal?: string; last_update?: string | null; data_issue?: string | null
}
type Snapshot = {
  ok: boolean; environment?: string; expert?: { version?: string | null }
  operational?: { status?: string; latest_contact?: string | null; broker_connected?: boolean | null }
  account?: { equity?: N; balance?: N; floating_pnl?: N; free_margin?: N }
  visibility?: { execution_input_enabled?: boolean; observation_mode?: boolean; halt_active?: boolean } | null
  external_experts?: External[]; symbols?: Sleeve[]; positions?: Position[]
  performance?: { closed_trades?: N; realized_pnl?: N }
  account_risk?: { status?: string; complete?: boolean } | null
  evidence?: {
    account_currency?: string; reconciliation?: { status?: string }
    archive_delivery?: { state?: string; pending?: N }
  }
}
const expected: Sleeve[] = [
  { symbol: 'USDJPY', timeframe: 'D1' }, { symbol: 'USDCHF', timeframe: 'D1' },
  { symbol: 'XAUUSD', timeframe: 'D1' }, { symbol: 'XAUUSD', timeframe: 'H4', experimental: true },
  { symbol: 'AMD', timeframe: 'H4', experimental: true },
]
const labels: Record<string, string> = {
  ONLINE: 'Telemetría conectada', STALE: 'Datos vencidos', NO_TELEMETRY: 'Sin telemetría',
  EXPERT_STOPPED: 'Expert detenido', BROKER_OFFLINE: 'Broker desconectado',
  WAITING_FOR_OBSERVER: 'Falta observador de cuenta', WAITING_FOR_IDENTITY: 'Identidad por confirmar',
  WAITING_FOR_PROBE: 'Falta sonda de riesgo', OBSERVING: 'Observación vigente', REVIEW_REQUIRED: 'Revisión necesaria',
  CURRENT: 'Evaluación vigente', MARKET_CLOSED: 'Sesión cerrada', PENDING: 'Evaluación pendiente',
  UNVERIFIED: 'Sin verificar', FEED_STALE: 'Cotización vencida', DATA_REVIEW: 'Revisar datos', STOPPED: 'Detenido',
  SESSION_CLOSED: 'Esperando apertura de sesión', QUOTE_NOT_FRESH: 'Esperando cotización fresca',
  STALE_OBSERVATION: 'Esperando captura actual', OBSERVE: 'Órdenes deshabilitadas', NO_DATA: 'Sin evaluación',
  EXECUTION_DISABLED: 'Ejecución deshabilitada', FLAT: 'Sin exposición', HOLD: 'Mantener posición',
  RISK_BLOCKED: 'Bloqueado por control de riesgo', RECONCILED: 'Conciliación correcta',
  IDLE: 'Al día', DELIVERED: 'Entrega confirmada', DISABLED: 'Deshabilitado', RETRY_PENDING: 'Reintento pendiente',
  MISSING: 'Sin registro recibido',
  WAIT_SESSION: 'Esperando sesión o cotización', ALREADY_EVALUATED: 'Vela ya evaluada',
  NOT_SENT: 'Sin solicitud enviada', NO_ACTION: 'Sin acción', OPEN_OK: 'Apertura aceptada',
  OPEN_FAIL: 'Apertura no confirmada', CLOSE_OK: 'Cierre aceptado', CLOSE_FAIL: 'Cierre no confirmado',
}
function label(value?: string | null) { return value ? labels[value] ?? value : 'Sin dato' }
function finite(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null }
function count(value: unknown) { const n = finite(value); return n == null ? 'Sin dato' : new Intl.NumberFormat('es-MX').format(n) }
function money(value: unknown, currency: string) {
  const n = finite(value)
  if (n == null) return 'Sin dato'
  try { return new Intl.NumberFormat('es-MX', { style: 'currency', currency, maximumFractionDigits: 2 }).format(n) }
  catch { return `${n.toFixed(2)} ${currency}` }
}
function date(value?: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Sin dato'
  return new Intl.DateTimeFormat('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Mexico_City' }).format(new Date(value))
}
function age(value: string | null | undefined, now: number): number | null {
  if (!value) return null
  const stamp = Date.parse(value)
  return Number.isFinite(stamp) ? now - stamp : null
}
function ago(value: string | null | undefined, now: number) {
  const elapsed = age(value, now)
  if (elapsed == null || elapsed < -120_000) return 'Hora sin verificar'
  const s = Math.max(0, Math.floor(elapsed / 1000))
  return s < 60 ? `Hace ${s} s` : s < 3600 ? `Hace ${Math.floor(s / 60)} min` : `Hace ${Math.floor(s / 3600)} h`
}
function Badge({ children, tone = 'muted' }: { children: ReactNode; tone?: 'good' | 'warn' | 'bad' | 'muted' }) {
  return <span className={`badge badge-${tone}`}><i aria-hidden="true" />{children}</span>
}
function Metric({ title, value, note, accent = false }: { title: string; value: string; note?: string; accent?: boolean }) {
  return <div className={`metric ${accent ? 'metric-accent' : ''}`}><span>{title}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>
}
function reason(value?: string | null) {
  const messages: Record<string, string> = {
    'Revalidate after session opens and a fresh quote arrives': 'Reevaluar al abrir la sesión y recibir una cotización fresca.',
    'Execution disabled or observation requested': 'Órdenes deshabilitadas o modo observación solicitado.',
    'terminal claim exists': 'Esta vela ya tiene una evaluación registrada en el terminal.',
  }
  return value ? messages[value] ?? value : null
}
function PositionCards({ rows, empty, currency, pending = false }: { rows: Position[]; empty: string; currency: string; pending?: boolean }) {
  return rows.length ? <div className="position-list">{rows.map((p, i) => {
    const types: Record<number, string> = { 2: 'Compra límite', 3: 'Venta límite', 4: 'Compra stop (BUY STOP)', 5: 'Venta stop', 6: 'Compra stop límite', 7: 'Venta stop límite' }
    const direction = p.direction?.toLowerCase()
    const side = pending && p.type != null ? types[p.type] ?? `Tipo ${p.type}` : direction === 'buy' ? 'Compra' : direction === 'sell' ? 'Venta' : p.direction ?? 'Dirección sin dato'
    return <div className="position" key={`${p.symbol}-${i}`}>
      <div><strong>{p.symbol ?? 'Símbolo sin dato'}</strong><span>{side} · {count(p.lots ?? p.volume)} lotes</span></div>
      <div><strong>{pending ? `Activación: ${finite(p.price) == null ? 'sin dato' : new Intl.NumberFormat('es-MX', { maximumFractionDigits: 5 }).format(p.price!)}` : money(p.pnl, currency)}</strong><span>SL {finite(p.sl) == null ? 'sin dato' : p.sl === 0 ? 'no establecido' : p.sl} · TP {finite(p.tp) == null ? 'sin dato' : p.tp === 0 ? 'sin objetivo fijo' : p.tp}</span></div>
    </div>
  })}</div> : <p className="empty-state">{empty}</p>
}
function GoldRush({ expert, currency, now }: { expert?: External; currency: string; now: number }) {
  const elapsed = age(expert?.observed_at, now)
  const fresh = elapsed != null && elapsed >= -120_000 && elapsed <= 120_000
  const status = expert?.status === 'OBSERVING' && !fresh ? 'STALE' : expert?.status ?? 'MISSING'
  const pending = Array.isArray(expert?.pending_orders) ? expert.pending_orders : null
  const positions = Array.isArray(expert?.positions) ? expert.positions : []
  return <section className="panel external-panel" aria-labelledby="goldrush-title">
    <div className="section-top"><div><p className="eyebrow">Expert externo · XAUUSD / H1</p><h2 id="goldrush-title">HobbieCode GoldRush</h2></div><Badge tone={status === 'OBSERVING' ? 'good' : 'warn'}>{label(status)}</Badge></div>
    <p className="section-copy">Sus posiciones y pendientes se observan por separado de PortfolioTrend. El total de la cuenta puede incluir ambos Experts.</p>
    <div className="external-metrics"><Metric title="Posiciones abiertas" value={count(expert?.open_positions)} note={finite(expert?.open_positions) != null ? 'Atribuidas al Expert' : 'Sin captura completa atribuible'} /><Metric title="Órdenes pendientes" value={pending ? count(pending.length) : 'Sin dato'} note="Todavía no son posiciones" /><Metric title="P&L flotante" value={money(expert?.floating_pnl, currency)} note="Posiciones atribuidas + swap" /></div>
    {(status === 'WAITING_FOR_OBSERVER' || status === 'MISSING') && <div className="notice">Falta una captura de AccountEvidenceObserver. Una apertura reportada en MT5 aún puede no aparecer aquí; los valores desconocidos no equivalen a cero.</div>}
    {status === 'WAITING_FOR_IDENTITY' && <div className="notice">La cuenta ya se observa, pero falta confirmar qué operaciones pertenecen a GoldRush.</div>}
    {status === 'STALE' && <div className="notice">La captura del observador está vencida. Estas cifras corresponden a la última observación, no al estado actual confirmado.</div>}
    <div className="split-detail"><div><h3>Posiciones</h3><PositionCards rows={positions} currency={currency} empty={expert?.open_positions === 0 ? 'La última captura atribuida no contiene posiciones abiertas.' : 'Sin detalle de posiciones verificado.'} /></div><div><h3>Pendientes</h3><PositionCards rows={pending ?? []} pending currency={currency} empty={pending ? 'La última captura no contiene pendientes atribuidas.' : 'Pendientes aún desconocidas.'} /></div></div>
    <div className="panel-foot"><span>Captura: {date(expert?.observed_at)} · {ago(expert?.observed_at, now)}</span><span>{expert?.history_complete === true ? 'Historial completo declarado' : 'Historial sin confirmar'}</span></div>
    {expert?.issues?.length ? <details><summary>Revisiones de atribución ({expert.issues.length})</summary><ul>{expert.issues.map(issue => <li key={issue}>{issue}</li>)}</ul></details> : null}
  </section>
}

function App() {
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastRead, setLastRead] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let cancelled = false
    let inFlight = false
    let controller: AbortController | null = null
    async function load() {
      if (inFlight) return
      inFlight = true
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 15_000)
      try {
        const response = await fetch('/api/v5-overview', { cache: 'no-store', signal: controller.signal })
        const body = await response.json() as Snapshot & { error?: string }
        if (!response.ok || !body.ok || !body.operational || !Array.isArray(body.symbols)) throw new Error(body.error || `Respuesta no disponible (${response.status})`)
        if (!cancelled) { setData(body); setError(null); setLastRead(new Date().toISOString()); setNow(Date.now()) }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error && cause.name !== 'AbortError' ? cause.message : 'La consulta agotó el tiempo de espera.')
      } finally { window.clearTimeout(timeout); inFlight = false }
    }
    void load()
    const poll = window.setInterval(() => { void load() }, 30_000)
    const clock = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => { cancelled = true; controller?.abort(); window.clearInterval(poll); window.clearInterval(clock) }
  }, [revision])
  const currency = data?.evidence?.account_currency ?? 'USD'
  const elapsed = age(data?.operational?.latest_contact, now)
  const validTime = elapsed != null && elapsed >= -120_000
  const transport = error ? 'ERROR' : !data ? 'LOADING' : !validTime ? 'NO_TELEMETRY' : elapsed > 35 * 60_000 ? 'STALE' : data.operational?.status ?? 'NO_TELEMETRY'
  const online = transport === 'ONLINE'
  const transportText = transport === 'ERROR' ? 'Consulta interrumpida' : transport === 'LOADING' ? 'Conectando…' : label(transport)
  const visibility = data?.visibility
  const execution = visibility?.halt_active === true ? 'HALT persistente' : visibility?.execution_input_enabled === false || visibility?.observation_mode === true ? 'Órdenes deshabilitadas por parámetros' : visibility?.execution_input_enabled === true ? 'Permiso por parámetros habilitado' : 'Permiso de ejecución sin verificar'
  const goldrush = data?.external_experts?.find(e => e.id === 'hobbiecode_goldrush')
  const sleeves = data?.symbols?.length ? data.symbols : expected
  const positions = data?.positions ?? []
  const archive = data?.evidence?.archive_delivery
  const risk = data?.account_risk
  return <main className="shell">
    <header className="masthead"><a href="#" className="brand"><span className="brand-mark">M</span><span>Momentum<span className="brand-sub">Trading / Control operativo</span></span></a><div className="masthead-status"><span className="demo-tag">Cuenta {data?.environment ?? 'sin confirmar'}</span><Badge tone={online ? 'good' : error ? 'bad' : 'warn'}>{transportText}</Badge></div></header>
    <section className="hero"><div><p className="eyebrow">Supervisión de MT5</p><h1>La cuenta y cada<br />estrategia, a la vista.</h1><p className="hero-copy">Posiciones, señales y estado de conexión con procedencia explícita. Una conexión vigente no confirma que un Expert tenga permiso para operar.</p></div><div className="freshness"><span className="freshness-icon" aria-hidden="true">↻</span><div><strong>{ago(data?.operational?.latest_contact, now)}</strong><p>Última captura · hora de México</p><time>{date(data?.operational?.latest_contact)}</time></div><button onClick={() => setRevision(v => v + 1)} aria-label="Consultar de nuevo el dashboard">Actualizar</button></div></section>
    {error && <div className="error-banner" role="alert"><strong>No se pudo actualizar el dashboard.</strong><span>{error} {data ? `Se conserva la lectura anterior de ${date(lastRead)}; no se confirma el estado actual.` : 'No hay cifras actuales confirmadas.'}</span></div>}
    {!data && !error && <div className="loading-message" role="status">Consultando la última captura disponible…</div>}
    <section className="account-grid" aria-label="Métricas de toda la cuenta"><Metric title="Equity de la cuenta" value={money(data?.account?.equity, currency)} note="Incluye todas las estrategias" accent /><Metric title="Balance" value={money(data?.account?.balance, currency)} note="Saldo registrado en el broker" /><Metric title="P&L flotante de cuenta" value={money(data?.account?.floating_pnl, currency)} note="No es sólo PortfolioTrend" /><Metric title="Margen libre" value={money(data?.account?.free_margin, currency)} note={`Divisa de cuenta: ${currency}`} /></section>
    <div className="operating-grid"><section className="panel portfolio-panel" aria-labelledby="portfolio-title"><div className="section-top"><div><p className="eyebrow">Motor multi-activo</p><h2 id="portfolio-title">PortfolioTrend</h2><span className="release">{data?.expert?.version ?? 'Versión aún sin confirmar'}</span></div><Badge tone={visibility?.execution_input_enabled === true && visibility?.observation_mode === false && !visibility?.halt_active ? 'good' : 'warn'}>{visibility?.observation_mode === true ? 'Modo observación' : 'Estado de ejecución'}</Badge></div>
      <div className={`execution-callout ${visibility?.execution_input_enabled === false ? 'execution-off' : ''}`}><span aria-hidden="true">◉</span><div><strong>{execution}</strong><p>{visibility?.execution_input_enabled === false || visibility?.observation_mode === true ? 'La telemetría puede estar conectada mientras este Expert no envía órdenes.' : 'Los permisos del terminal, los controles y una señal válida también deben cumplirse.'}</p></div></div>
      <div className="portfolio-stats"><Metric title="Posiciones propias" value={data ? count(positions.length) : 'Sin dato'} /><Metric title="Cierres atribuidos" value={count(data?.performance?.closed_trades)} /><Metric title="P&L realizado propio" value={money(data?.performance?.realized_pnl, currency)} /></div>
      <PositionCards rows={positions} currency={currency} empty={data ? 'La captura de PortfolioTrend no contiene posiciones propias. Esto no descarta exposición de GoldRush.' : 'Esperando captura de posiciones.'} />
      <div className="panel-foot"><span>Broker: {data?.operational?.broker_connected === true ? 'conectado en la captura' : data?.operational?.broker_connected === false ? 'desconectado' : 'sin confirmar'}</span><span>HALT: {visibility?.halt_active === true ? 'activo' : visibility?.halt_active === false ? 'no observado' : 'sin dato'}</span></div>
    </section><aside className="panel pipeline-panel"><p className="eyebrow">Integridad del flujo</p><h2>Datos con contexto</h2><div className="pipeline-item"><span>01</span><div><strong>Captura MT5</strong><p>{date(data?.operational?.latest_contact)}</p></div><Badge tone={online ? 'good' : 'warn'}>{online ? 'Vigente' : 'Sin confirmar'}</Badge></div><div className="pipeline-item"><span>02</span><div><strong>Conciliación</strong><p>{label(data?.evidence?.reconciliation?.status)}</p></div></div><div className="pipeline-item"><span>03</span><div><strong>Archivo privado</strong><p>{label(archive?.state)} · pendientes: {count(archive?.pending)}</p></div></div><div className="pipeline-item"><span>04</span><div><strong>Observación de riesgo</strong><p>{label(risk?.status)}{risk?.complete === false ? ' · cobertura incompleta' : ''}</p></div></div><p className="pipeline-note">Si falta el observador o la sonda, la exposición externa y el riesgo de cuenta siguen sin confirmar.</p></aside></div>
    <GoldRush expert={goldrush} currency={currency} now={now} />
    <section className="panel sleeves-section" aria-labelledby="sleeves-title"><div className="section-top"><div><p className="eyebrow">Asignación de PortfolioTrend</p><h2 id="sleeves-title">Cinco mangas, una instancia</h2></div><span className="quiet">D1: 20/10 · SMA200 &nbsp; H4: 60/30 · SMA600</span></div><div className="sleeves-grid">{sleeves.map(s => <article className="sleeve" key={`${s.symbol}-${s.timeframe}`}><div className="sleeve-title"><h3>{s.symbol}</h3><span>{s.timeframe}</span></div><span className={`sleeve-kind ${s.experimental ? 'experimental' : ''}`}>{s.experimental ? 'Experimental' : 'Núcleo'}</span><p className="sleeve-health">{error ? 'Última lectura conservada' : label(s.analysis_health)}</p><dl><div><dt>Señal registrada</dt><dd>{s.signal === 'BUY' ? 'Compra' : s.signal === 'SELL' ? 'Venta' : s.signal === 'FLAT' ? 'Neutral' : 'Sin dato'}</dd></div><div><dt>Estado de orden</dt><dd>{label(s.order_status)}</dd></div></dl><p className="sleeve-reason">{reason(s.order_message) || s.data_issue || (s.current_wait_reason ? label(s.current_wait_reason) : 'Esperando próxima evaluación válida.')}</p><time>Evaluación: {date(s.last_update)}</time></article>)}</div></section>
    <footer><span>Lectura automática cada 30 s · Horarios en Ciudad de México</span><span>La apertura de una posición se confirma con evidencia del broker.</span><span>Última consulta correcta: {date(lastRead)}</span></footer>
  </main>
}
export default App
