import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { installWakeRefresh } from './wake-refresh.ts'
import './App.css'

type N = number | null
type Position = { symbol?: string; direction?: string; type?: number; lots?: N; volume?: N; price?: N; sl?: N; tp?: N; pnl?: N; initial_risk_estimate?: N; entry_initial_risk_estimate?: N; remaining_risk_estimate?: N }
type External = {
  id?: string; name?: string; symbol?: string; timeframe?: string; status?: string; observed_at?: string | null; open_positions?: N
  pending_orders?: Position[] | null; positions?: Position[]; floating_pnl?: N
  history_complete?: boolean; issues?: string[]
  attribution_basis?: string; expert_running_verified?: boolean; evaluation_started_at?: string | null
  realized_cash_pnl?: N; performance?: { closed_trades?: N }; trades?: unknown[]
}
type Sleeve = {
  symbol: string; timeframe: string; experimental?: boolean; analysis_health?: string
  order_status?: string; order_message?: string | null; current_wait_reason?: string | null
  signal?: string; last_update?: string | null; data_issue?: string | null
  last_bar?: string | null; discard_reason?: string | null; reason_code?: string | null
  potential_direction?: string | null; entry_ready?: boolean; close?: N; sma?: N
  channel_high?: N; channel_low?: N; exit_trigger_price?: N; distance_to_trigger_pct?: N
}
type Research = {
  symbol?: string; timeframe?: string; status?: string; execution_enabled?: boolean
  bar_time?: string | null; sample_returns?: N; momentum_20_pct?: N
  annualized_volatility_pct?: N; proposal?: string
}
type Snapshot = {
  ok: boolean; environment?: string; expert?: { version?: string | null }
  operational?: { status?: string; latest_contact?: string | null; broker_connected?: boolean | null; evaluations_24h?: N; entry_signals_24h?: N }
  account?: { equity?: N; balance?: N; floating_pnl?: N; free_margin?: N }
  visibility?: { execution_input_enabled?: boolean; observation_mode?: boolean; halt_active?: boolean } | null
  external_experts?: External[]; symbols?: Sleeve[]; positions?: Position[]
  asset_research?: Research[]
  research_evidence?: ResearchEvidence | null
  execution_audit?: { requests_24h?: N; confirmed_deals_24h?: N; rejected_24h?: N; observed_at?: string | null; rows?: ExecutionRow[] } | null
  execution_policy?: { sizing_mode?: string; mode?: string; fixed_lots?: N; fixed_amd_lots?: N; per_trade_pct?: N; take_profit_r?: N; portfolio_pct?: N; gold_pct?: N } | null
  performance?: { closed_trades?: N; realized_pnl?: N }
  account_risk?: { status?: string; complete?: boolean } | null
  evidence?: {
    account_currency?: string; reconciliation?: { status?: string }
    archive_delivery?: { state?: string; pending?: N }
    observation_max_age_seconds?: N
  }
}
type ExecutionRow = { request_id?: string; observed_at?: string | null; symbol?: string; timeframe?: string; action?: string; status?: string; requested_lots?: N; requested_sl?: N; requested_tp?: N; broker_retcode?: N; broker_order_ticket?: string | null; broker_deal_ticket?: string | null; fill_price?: N; fill_confirmed?: boolean }
type ResearchEvidence = {
  status?: string; freshness?: string; as_of_utc?: string | null; generated_at_utc?: string | null
  decision_count?: N; entry_candidate_count?: N; linked_closed_trades?: N; unlinked_execution_events?: N
  mature_hypothetical_outcomes?: N; active_release_id?: string | null; source_candidate?: string | null
  source_candidate_active?: boolean
  feature_coverage?: Record<string, { known?: N; total?: N }>
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
  STAGED: 'Encolado al crear la captura',
  WAIT_SESSION: 'Esperando sesión o cotización', ALREADY_EVALUATED: 'Vela ya evaluada',
  NOT_SENT: 'Sin solicitud enviada', NO_ACTION: 'Sin acción', OPEN_OK: 'Apertura aceptada',
  OPEN_FAIL: 'Apertura no confirmada', CLOSE_OK: 'Cierre aceptado', CLOSE_FAIL: 'Cierre no confirmado',
  REQUEST_RECORDED: 'Solicitud registrada', BROKER_DEAL_CONFIRMED: 'Ejecución confirmada por deal',
  RESULT_RECORDED_NO_FILL_PROOF: 'Respuesta recibida · ejecución sin confirmar', BROKER_REJECTED: 'Rechazo del broker', CONFLICT_REQUIRES_REVIEW: 'Identificadores en conflicto',
  UNKNOWN: 'Sin evaluación confirmada', DESCRIPTIVE_ONLY: 'Análisis descriptivo',
  SYMBOL_UNAVAILABLE: 'Símbolo no disponible', INSUFFICIENT_HISTORY: 'Histórico insuficiente', INVALID_HISTORY: 'Histórico por revisar',
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
function barDate(value?: string | null) {
  if (!value) return 'Sin dato'
  // Naive bar timestamps are broker wall-clock values, not UTC observations.
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(value) ? `${value.replace('T', ' ')} · broker` : date(value)
}
function decimal(value: unknown, digits = 5) {
  const n = finite(value)
  return n == null ? 'Sin dato' : new Intl.NumberFormat('es-MX', { maximumFractionDigits: digits }).format(n)
}
function percent(value: unknown) { const n = finite(value); return n == null ? 'Sin dato' : `${decimal(n, 2)}%` }
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
      <div><strong>{pending ? `Activación: ${finite(p.price) == null ? 'sin dato' : new Intl.NumberFormat('es-MX', { maximumFractionDigits: 5 }).format(p.price!)}` : money(p.pnl, currency)}</strong><span>SL {finite(p.sl) == null ? 'sin dato' : p.sl === 0 ? 'no establecido' : p.sl} · TP {finite(p.tp) == null ? 'sin dato' : p.tp === 0 ? 'sin objetivo fijo' : p.tp}</span>{!pending && (finite(p.initial_risk_estimate) != null || finite(p.entry_initial_risk_estimate) != null || finite(p.remaining_risk_estimate) != null) && <span>Riesgo inicial estimado {money(p.entry_initial_risk_estimate ?? p.initial_risk_estimate, currency)} · riesgo restante a SL {money(p.remaining_risk_estimate, currency)}</span>}</div>
    </div>
  })}</div> : <p className="empty-state">{empty}</p>
}
function ExternalPanel({ expert, currency, now }: { expert?: External; currency: string; now: number }) {
  const elapsed = age(expert?.observed_at, now)
  const fresh = elapsed != null && elapsed >= -120_000 && elapsed <= 120_000
  const status = expert?.status === 'OBSERVING' && !fresh ? 'STALE' : expert?.status ?? 'MISSING'
  const pending = Array.isArray(expert?.pending_orders) ? expert.pending_orders : null
  const positions = Array.isArray(expert?.positions) ? expert.positions : []
  const titleId = !expert || expert.id === 'hobbiecode_goldrush' ? 'goldrush-title' : `external-${expert.id ?? 'unverified'}`
  return <section className="panel external-panel" aria-labelledby={titleId}>
    <div className="section-top"><div><p className="eyebrow">Expert externo · {expert ? expert.symbol ?? 'Símbolo sin confirmar' : 'XAUUSD'} / {expert ? expert.timeframe ?? 'Temporalidad sin confirmar' : 'H1'}</p><h2 id={titleId}>{expert ? expert.name ?? 'Expert externo sin identidad' : 'HobbieCode GoldRush'}</h2></div><Badge tone={status === 'OBSERVING' ? 'good' : 'warn'}>{label(status)}</Badge></div>
    <p className="section-copy">Posiciones y pendientes atribuidas por separado de PortfolioTrend. {expert?.attribution_basis === 'CONFIGURED_MAGIC' ? 'Atribución por magic configurado; no acredita una operación nueva.' : expert?.attribution_basis === 'BROKER_ORDER_LINK' ? 'Identidad vinculada mediante evidencia de órdenes del broker.' : 'La identidad depende de la evidencia recibida.'} {expert?.expert_running_verified !== true && 'El observador no confirma que este EA esté ejecutándose.'}</p>
    <div className="external-metrics"><Metric title="Posiciones abiertas" value={count(expert?.open_positions)} note={finite(expert?.open_positions) != null ? 'Atribuidas al Expert' : 'Sin captura completa atribuible'} /><Metric title="Órdenes pendientes" value={pending ? count(pending.length) : 'Sin dato'} note="Todavía no son posiciones" /><Metric title="P&L flotante" value={money(expert?.floating_pnl, currency)} note="Posiciones atribuidas + swap" /></div>
    {(status === 'WAITING_FOR_OBSERVER' || status === 'MISSING') && <div className="notice">Falta una captura del observador de cuenta. Una apertura reportada en MT5 aún puede no aparecer aquí; los valores desconocidos no equivalen a cero.</div>}
    {status === 'WAITING_FOR_IDENTITY' && <div className="notice">La cuenta ya se observa, pero falta confirmar qué operaciones pertenecen a este Expert.</div>}
    {status === 'STALE' && <div className="notice">La captura del observador está vencida. Estas cifras corresponden a la última observación, no al estado actual confirmado.</div>}
    <div className="split-detail"><div><h3>Posiciones</h3><PositionCards rows={positions} currency={currency} empty={expert?.open_positions === 0 ? 'La última captura atribuida no contiene posiciones abiertas.' : 'Sin detalle de posiciones verificado.'} /></div><div><h3>Pendientes</h3><PositionCards rows={pending ?? []} pending currency={currency} empty={pending ? 'La última captura no contiene pendientes atribuidas.' : 'Pendientes aún desconocidas.'} /></div></div>
    <div className="panel-foot"><span>Captura: {date(expert?.observed_at)} · {ago(expert?.observed_at, now)}</span><span>{expert?.history_complete === true ? 'Historial completo declarado' : 'Historial sin confirmar'}</span></div>
    <details><summary>Historial atribuido · {count(expert?.performance?.closed_trades)} cierres</summary><p className="section-copy">Periodo registrado: desde {date(expert?.evaluation_started_at)} hasta la captura de {date(expert?.observed_at)}. Estos cierres no se atribuyen automáticamente a hoy o ayer.</p><div className="external-history"><Metric title="Cierres del historial" value={count(expert?.performance?.closed_trades)} /><Metric title="Resultado realizado en deals" value={money(expert?.realized_cash_pnl, currency)} note="Incluye costes y cierres parciales; no sólo posiciones completamente cerradas" /></div></details>
    {expert?.issues?.length ? <details><summary>Revisiones de atribución ({expert.issues.length})</summary><ul>{expert.issues.map(issue => <li key={issue}>{issue}</li>)}</ul></details> : null}
  </section>
}

function SleeveCard({ sleeve: s, current }: { sleeve: Sleeve; current: boolean }) {
  const direction = s.potential_direction === 'BUY' ? 'Alcista' : s.potential_direction === 'SELL' ? 'Bajista' : 'Sin dirección confirmada'
  return <article className={`sleeve ${current ? '' : 'is-stale'}`}>
    <div className="sleeve-title"><h3>{s.symbol}</h3><span>{s.timeframe}</span></div>
    <span className={`sleeve-kind ${s.experimental ? 'experimental' : ''}`}>{s.experimental ? 'Experimental' : 'Núcleo'}</span>
    <p className="sleeve-health">{current ? label(s.analysis_health) : 'Último registro · vigencia sin confirmar'}</p>
    <p className="analysis-decision"><span>{current ? 'Análisis de la última vela' : 'Análisis conservado'}</span>{s.discard_reason ?? 'Todavía no hay razonamiento de señal disponible.'}</p>
    <dl>
      <div><dt>Dirección del contexto</dt><dd>{direction}</dd></div>
      <div><dt>Señal registrada</dt><dd>{s.signal === 'BUY' ? 'Compra' : s.signal === 'SELL' ? 'Venta' : s.signal === 'FLAT' ? 'Neutral' : 'Sin dato'}</dd></div>
      <div><dt>Cierre / media SMA</dt><dd>{decimal(s.close)} / {decimal(s.sma)}</dd></div>
      <div><dt>Canal de entrada: piso – techo</dt><dd>{decimal(s.channel_low)} – {decimal(s.channel_high)}</dd></div>
      <div><dt>Distancia al gatillo</dt><dd>{percent(s.distance_to_trigger_pct)}</dd></div>
      <div><dt>Estado de orden</dt><dd>{label(s.order_status)}</dd></div>
    </dl>
    <p className="sleeve-reason">{!current ? 'Esperando una captura reciente; la decisión conservada no confirma una oportunidad actual.' : (s.current_wait_reason ? label(s.current_wait_reason) : reason(s.order_message) || s.data_issue || 'Esperando próxima evaluación válida.')}</p>
    <time>Vela: {barDate(s.last_bar)}</time><time>Evaluación: {date(s.last_update)}</time>
  </article>
}

function ResearchPanel({ rows, current }: { rows: Research[]; current: boolean }) {
  return <section className="panel research-section" aria-labelledby="research-title">
    <div className="section-top"><div><p className="eyebrow">Fuera de las cinco mangas de ejecución</p><h2 id="research-title">Seguimiento de otros activos</h2></div><Badge tone={current ? 'muted' : 'warn'}>{current ? `${rows.length} activos recibidos` : 'Análisis conservado'}</Badge></div>
    <p className="section-copy">Estadísticas D1 de los símbolos configurados para investigación. No son posiciones, órdenes ni activos habilitados para operar. La lista depende de los datos recibidos de MT5.</p>
    {!current && rows.length > 0 && <div className="notice">No se confirma la vigencia de la fuente. Los escenarios y estadísticas de abajo corresponden al último registro, aunque esta página se consulte ahora.</div>}
    <div className="research-grid">{rows.map((r, index) => <article className="research-card" key={`${r.symbol}-${r.timeframe}-${index}`}>
      <div className="sleeve-title"><h3>{r.symbol ?? 'Sin símbolo'}</h3><span>{r.timeframe ?? 'Sin temporalidad'}</span></div>
      <span className="research-scope">{r.execution_enabled === false ? 'Sin ejecución' : 'Alcance sin confirmar'}</span>
      <p className="research-status">{label(r.status)}</p>
      <dl><div><dt>Momentum de 20 velas</dt><dd>{percent(r.momentum_20_pct)}</dd></div><div><dt>Volatilidad anualizada</dt><dd>{percent(r.annualized_volatility_pct)}</dd></div><div><dt>Escenario descriptivo</dt><dd>{r.proposal === 'RESEARCH_LONG' ? 'Hipótesis alcista' : r.proposal === 'RESEARCH_SHORT' ? 'Hipótesis bajista' : r.proposal === 'WATCH' ? 'En seguimiento' : 'Sin dato'}</dd></div></dl>
      <p className="research-foot">Muestra: {count(r.sample_returns)} retornos</p><time>Vela: {barDate(r.bar_time)}</time>
    </article>)}</div>
    {rows.length === 0 && <p className="empty-state">La captura recibida todavía no contiene análisis de otros activos. Esto no los habilita ni supone que no existan en MT5.</p>}
  </section>
}

function ResearchEvidencePanel({ row }: { row?: ResearchEvidence | null }) {
  const fresh = row?.freshness === 'AT_RECORDED_CUTOFF'
  return <section className="panel research-section" aria-labelledby="research-evidence-title"><div className="section-top"><div><p className="eyebrow">Decisiones y resultados</p><h2 id="research-evidence-title">Evidencia para mejorar la estrategia</h2></div><Badge tone={fresh ? 'good' : 'warn'}>{!row ? 'Dataset pendiente' : fresh ? 'Dataset al corte indicado' : 'Vigencia sin confirmar'}</Badge></div>
    <p className="section-copy">Dataset de investigación generado bajo demanda. El refresco de esta página no reconstruye el dataset. Los resultados hipotéticos se mantienen separados de las operaciones reales; esta información no cambia entradas ni lotajes.</p>
    {row ? <><div className="external-metrics"><Metric title="Decisiones únicas" value={count(row.decision_count)} note="No son snapshots ni operaciones" /><Metric title="Candidatos de entrada" value={count(row.entry_candidate_count)} note="No confirman una orden enviada" /><Metric title="Cierres vinculados" value={count(row.linked_closed_trades)} note="Sólo enlaces explícitos a decisiones" /></div>
      <p className="notice">Sin validación de rentabilidad. Los datos disponibles todavía deben superar una comparación temporal con costes y evidencia suficiente.</p>
      <details><summary>Cobertura y procedencia de investigación</summary><p className="section-copy">Versión observada al corte: {row.active_release_id ?? 'Sin confirmar'}. Instrumentación candidata: {row.source_candidate ?? 'Sin confirmar'} · {row.source_candidate_active === true ? 'Observada en este dataset' : 'Todavía no observada en este dataset'}.</p><dl className="research-coverage">{[['atr', 'ATR'], ['spread_atr_ratio', 'Spread / ATR'], ['entry_distance_atr', 'Distancia al canal / ATR'], ['htf_context', 'Contexto de temporalidad superior']].map(([key, name]) => <div key={key}><dt>{name}</dt><dd>{count(row.feature_coverage?.[key]?.known)} / {count(row.feature_coverage?.[key]?.total)} decisiones</dd></div>)}</dl><p className="section-copy">Eventos de ejecución sin vínculo: {count(row.unlinked_execution_events)}. Resultados hipotéticos maduros: {count(row.mature_hypothetical_outcomes)}. Los desconocidos no equivalen a cero.</p></details>
      <div className="panel-foot"><span>Datos hasta: {date(row.as_of_utc)}</span><span>Dataset generado: {date(row.generated_at_utc)}</span></div></> : <p className="empty-state">Esperando un resumen verificable del dataset. No se infiere una mejora de estrategia a partir de la conexión o del número de capturas.</p>}
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
    // Timers can be throttled or suspended with the tab/laptop. Refresh on return
    // instead of waiting for the next background interval to become eligible.
    const removeWakeListeners = installWakeRefresh(document, window, () => { setNow(Date.now()); setRevision(v => v + 1) })
    const offline = () => { setNow(Date.now()); setError('El navegador indica que no hay conexión de red.') }
    window.addEventListener('offline', offline)
    return () => {
      cancelled = true; controller?.abort(); window.clearInterval(poll); window.clearInterval(clock)
      removeWakeListeners(); window.removeEventListener('offline', offline)
    }
  }, [revision])
  const currency = data?.evidence?.account_currency ?? 'USD'
  const elapsed = age(data?.operational?.latest_contact, now)
  const validTime = elapsed != null && elapsed >= -120_000
  const freshnessLimitMs = (finite(data?.evidence?.observation_max_age_seconds) ?? 180) * 1000
  const transport = error ? 'ERROR' : !data ? 'LOADING' : !validTime ? 'NO_TELEMETRY' : elapsed > freshnessLimitMs ? 'STALE' : data.operational?.status ?? 'NO_TELEMETRY'
  const online = transport === 'ONLINE'
  const transportText = transport === 'ERROR' ? 'Consulta interrumpida' : transport === 'LOADING' ? 'Conectando…' : label(transport)
  const visibility = data?.visibility
  const execution = visibility?.halt_active === true ? 'HALT persistente' : visibility?.execution_input_enabled === false || visibility?.observation_mode === true ? 'Órdenes deshabilitadas por parámetros' : visibility?.execution_input_enabled === true ? 'Permiso por parámetros habilitado' : 'Permiso de ejecución sin verificar'
  const externalExperts = Array.isArray(data?.external_experts) ? data.external_experts.filter(e => e && typeof e === 'object') : []
  const sleeves = data?.symbols?.length ? data.symbols : expected
  const positions = data?.positions ?? []
  const archive = data?.evidence?.archive_delivery
  const risk = data?.account_risk
  const research = Array.isArray(data?.asset_research) ? data.asset_research.filter(r => r && typeof r.symbol === 'string') : []
  return <main className="shell">
    <header className="masthead"><a href="#" className="brand"><span className="brand-mark">M</span><span>Momentum<span className="brand-sub">Trading / Control operativo</span></span></a><div className="masthead-status"><span className="demo-tag">Cuenta {data?.environment ?? 'sin confirmar'}</span><Badge tone={online ? 'good' : error ? 'bad' : 'warn'}>{transportText}</Badge></div></header>
    <section className="hero"><div><p className="eyebrow">Supervisión de MT5</p><h1>La cuenta y cada<br />estrategia, a la vista.</h1><p className="hero-copy">Posiciones, señales y estado de conexión con procedencia explícita. Una conexión vigente no confirma que un Expert tenga permiso para operar.</p></div><div className="freshness"><span className="freshness-icon" aria-hidden="true">↻</span><div><strong>{ago(data?.operational?.latest_contact, now)}</strong><p>Última captura · hora de México</p><time>{date(data?.operational?.latest_contact)}</time></div><button onClick={() => setRevision(v => v + 1)} aria-label="Consultar de nuevo el dashboard">Actualizar</button></div></section>
    {error && <div className="error-banner" role="alert"><strong>No se pudo actualizar el dashboard.</strong><span>{error} {data ? `Se conserva la lectura anterior de ${date(lastRead)}; no se confirma el estado actual.` : 'No hay cifras actuales confirmadas.'}</span></div>}
    {!error && transport === 'STALE' && <div className="notice source-stale" role="status"><strong>La página responde, pero MT5 no entrega una captura reciente.</strong><span>Última captura: {date(data?.operational?.latest_contact)}. Consultar de nuevo no convierte estos datos en actuales; se espera una nueva observación del terminal y del relay.</span></div>}
    {!data && !error && <div className="loading-message" role="status">Consultando la última captura disponible…</div>}
    <nav className="section-nav" aria-label="Secciones del dashboard"><a href="#account-summary">Cuenta</a><a href="#portfolio-title">PortfolioTrend</a><a href="#external-experts-title">Experts externos{externalExperts.length ? ` (${externalExperts.length})` : ''}</a><a href="#sleeves-title">Cinco mangas</a><a href="#research-title">Otros activos{research.length ? ` (${research.length})` : ''}</a></nav>
    <section className="account-grid" id="account-summary" aria-label="Métricas de toda la cuenta"><Metric title="Equity de la cuenta" value={money(data?.account?.equity, currency)} note="Incluye todas las estrategias" accent /><Metric title="Balance" value={money(data?.account?.balance, currency)} note="Saldo registrado en el broker" /><Metric title="P&L flotante de cuenta" value={money(data?.account?.floating_pnl, currency)} note="No es sólo PortfolioTrend" /><Metric title="Margen libre" value={money(data?.account?.free_margin, currency)} note={`Divisa de cuenta: ${currency}`} /></section>
    <div className="operating-grid"><section className="panel portfolio-panel" aria-labelledby="portfolio-title"><div className="section-top"><div><p className="eyebrow">Motor multi-activo</p><h2 id="portfolio-title">PortfolioTrend</h2><span className="release">{data?.expert?.version ?? 'Versión aún sin confirmar'}</span></div><Badge tone={visibility?.execution_input_enabled === true && visibility?.observation_mode === false && !visibility?.halt_active ? 'good' : 'warn'}>{visibility?.observation_mode === true ? 'Modo observación' : 'Estado de ejecución'}</Badge></div>
      <div className={`execution-callout ${visibility?.execution_input_enabled === false ? 'execution-off' : ''}`}><span aria-hidden="true">◉</span><div><strong>{execution}</strong><p>{visibility?.execution_input_enabled === false || visibility?.observation_mode === true ? 'La telemetría puede estar conectada mientras este Expert no envía órdenes.' : 'Los permisos del terminal, los controles y una señal válida también deben cumplirse.'}</p></div></div>
      <div className="portfolio-stats"><Metric title="Posiciones propias" value={data ? count(positions.length) : 'Sin dato'} /><Metric title="Cierres atribuidos" value={count(data?.performance?.closed_trades)} /><Metric title="P&L realizado propio" value={money(data?.performance?.realized_pnl, currency)} /></div>
      <p className="activity-summary">Últimas 24 h de observaciones disponibles: <strong>{count(data?.operational?.evaluations_24h)}</strong> evaluaciones registradas · <strong>{count(data?.operational?.entry_signals_24h)}</strong> señales de entrada. Una evaluación neutral no es una orden.</p>
      {data?.execution_policy && <p className="activity-summary">{data.execution_policy.sizing_mode === 'FIXED_VOLUME_DEMO' ? `Lote fijo demo: ${decimal(data.execution_policy.fixed_lots, 2)} · AMD ${decimal(data.execution_policy.fixed_amd_lots, 2)}. El riesgo monetario se calcula para cada posición y su SL.` : data.execution_policy.sizing_mode === 'RISK_PERCENT' ? `Tamaño por riesgo: ${percent(data.execution_policy.per_trade_pct)} por entrada.` : 'Modo de cálculo de tamaño sin confirmar.'} TP configurado: {decimal(data.execution_policy.take_profit_r, 2)} R de la distancia inicial al SL.</p>}
      <details><summary>Órdenes y protecciones registradas</summary><p className="section-copy">Últimas 24 h al corte de {date(data?.execution_audit?.observed_at)}: {count(data?.execution_audit?.requests_24h)} solicitudes · {count(data?.execution_audit?.confirmed_deals_24h)} ejecuciones vinculadas a deals · {count(data?.execution_audit?.rejected_24h)} rechazos. Una respuesta del broker sin deal vinculado conserva ejecución sin confirmar.</p>
        {data?.execution_audit?.rows?.length ? <div className="position-list">{data.execution_audit.rows.map((row, index) => <div className="position" key={row.request_id ?? index}><div><strong>{row.symbol} {row.timeframe} · {row.action}</strong><span>{label(row.status)} · {date(row.observed_at)}</span><span>{count(row.requested_lots)} lotes · SL solicitado {decimal(row.requested_sl)} · TP solicitado {decimal(row.requested_tp)}</span></div><div><strong>{row.fill_confirmed ? `Precio ejecutado ${decimal(row.fill_price)}` : 'Sin fill confirmado'}</strong><span>Retcode {count(row.broker_retcode)} · orden {row.broker_order_ticket ?? 'sin confirmar'} · deal {row.broker_deal_ticket ?? 'sin confirmar'}</span></div></div>)}</div> : <p className="empty-state">Sin solicitudes registradas en la evidencia disponible.</p>}
      </details>
      <PositionCards rows={positions} currency={currency} empty={data ? 'La captura de PortfolioTrend no contiene posiciones propias. Esto no descarta exposición de otros Experts.' : 'Esperando captura de posiciones.'} />
      <div className="panel-foot"><span>Broker: {data?.operational?.broker_connected === true ? 'conectado en la captura' : data?.operational?.broker_connected === false ? 'desconectado' : 'sin confirmar'}</span><span>HALT: {visibility?.halt_active === true ? 'activo' : visibility?.halt_active === false ? 'no observado' : 'sin dato'}</span></div>
    </section><aside className="panel pipeline-panel"><p className="eyebrow">Integridad del flujo</p><h2>Datos con contexto</h2><div className="pipeline-item"><span>01</span><div><strong>Captura MT5</strong><p>{date(data?.operational?.latest_contact)}</p></div><Badge tone={online ? 'good' : 'warn'}>{online ? 'Vigente' : 'Sin confirmar'}</Badge></div><div className="pipeline-item"><span>02</span><div><strong>Conciliación</strong><p>{label(data?.evidence?.reconciliation?.status)}</p></div></div><div className="pipeline-item"><span>03</span><div><strong>Archivo privado</strong><p>{label(archive?.state)} · pendientes en esa captura: {count(archive?.pending)}</p><p>Estado al formar la captura, antes del acuse de su propia entrega; no confirma un atasco actual.</p></div></div><div className="pipeline-item"><span>04</span><div><strong>Observación de riesgo</strong><p>{label(risk?.status)}{risk?.complete === false ? ' · cobertura incompleta' : ''}</p></div></div><p className="pipeline-note">Si falta el observador o la sonda, la exposición externa y el riesgo de cuenta siguen sin confirmar.</p></aside></div>
    <section aria-labelledby="external-experts-title"><div className="section-top"><div><p className="eyebrow">Fuentes externas recibidas</p><h2 id="external-experts-title">Experts externos</h2></div><span className="quiet">Observar una cuenta no acredita ejecución del EA.</span></div>{externalExperts.length ? externalExperts.map((expert, index) => <ExternalPanel key={expert.id ?? index} expert={expert} currency={currency} now={now} />) : <ExternalPanel currency={currency} now={now} />}</section>
    <section className="panel sleeves-section" aria-labelledby="sleeves-title"><div className="section-top"><div><p className="eyebrow">Asignación de PortfolioTrend</p><h2 id="sleeves-title">Cinco mangas, una instancia</h2></div><span className="quiet">D1: 20/10 · SMA200 &nbsp; H4: 60/30 · SMA600</span></div><div className="sleeves-grid">{sleeves.map(s => <SleeveCard key={`${s.symbol}-${s.timeframe}`} sleeve={s} current={online} />)}</div></section>
    <ResearchEvidencePanel row={data?.research_evidence} />
    <ResearchPanel rows={research} current={online} />
    <footer><span>Lectura automática cada 30 s · Horarios en Ciudad de México</span><span>La apertura de una posición se confirma con evidencia del broker.</span><span>Última consulta correcta: {date(lastRead)}</span></footer>
  </main>
}
export default App
