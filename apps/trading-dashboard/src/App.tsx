import { useEffect, useMemo, useState } from 'react'
import './App.css'

type ApiState<T> = {
  loading: boolean
  error: string | null
  data: T | null
}

type ApiRows<T> = {
  ok: boolean
  rows: T[]
  error?: string
}

type DataQualityResponse = {
  ok: boolean
  cutoff: string
  summary: {
    live_signal_evals_checked: number
    live_incomplete_signal_evals: number
    live_trades_checked: number
    live_incomplete_trade_opens: number
    live_incomplete_trade_closes: number
    latest_signal_is_pre_bug_data_01: boolean
    latest_signal_raw_payload_ok: boolean
    latest_signal_context_ok: boolean
  }
  latest_signal: SignalEval | null
  samples: Record<string, unknown[]>
  error?: string
}

type Trade = {
  created_at: string
  symbol: string
  position_id: number | string | null
  ticket: number | string | null
  direction: string | null
  open_time: string | null
  open_price: number | null
  sl: number | null
  tp: number | null
  lots: number | null
  close_time: string | null
  close_price: number | null
  pnl: number | null
  close_reason: string | null
  ea_version: string | null
  event_type: string | null
  phase: string | null
  ledger_classification?: string | null
  exclude_from_edge?: boolean | null
  data_quality_notes?: string | null
}

type SignalEval = {
  created_at: string
  symbol: string
  eval_time: string | null
  action: string | null
  block_reason: string | null
  direction: string | null
  entry_price: number | null
  sl_price: number | null
  tp_price: number | null
  atr_h4: number | null
  distance_to_ema_atr: number | null
  trend_state: string | null
  volatility_state: string | null
  session: string | null
  bias_d1: number | null
  spread_atr_ratio: number | null
  raw_payload: unknown | null
  ea_version: string | null
  phase: string | null
}

function useApi<T>(path: string): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({
    loading: true,
    error: null,
    data: null,
  })

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const res = await fetch(path, { cache: 'no-store' })
        const json = await res.json()

        if (!res.ok || json.ok === false) {
          throw new Error(json.error || `Request failed: ${res.status}`)
        }

        if (!cancelled) {
          setState({ loading: false, error: null, data: json })
        }
      } catch (err) {
        if (!cancelled) {
          setState({
            loading: false,
            error: err instanceof Error ? err.message : String(err),
            data: null,
          })
        }
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [path])

  return state
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-MX', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value))
}

function formatNumber(value: number | null | undefined, digits = 5): string {
  if (value == null) return '—'
  return Number(value).toFixed(digits)
}

function statusClass(ok: boolean): string {
  return ok ? 'status-ok' : 'status-warn'
}

function Badge({
  children,
  tone = 'neutral',
}: {
  children: string
  tone?: 'ok' | 'warn' | 'neutral'
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

function PriceStack({ trade }: { trade: Trade }) {
  return (
    <div className="stack">
      <span>Open {formatNumber(trade.open_price)}</span>
      <span>SL {formatNumber(trade.sl)}</span>
      <span>TP {formatNumber(trade.tp)}</span>
    </div>
  )
}

function OpenPositionsTable({ rows }: { rows: Trade[] }) {
  return (
    <div className="table-wrap">
      <table className="table-compact">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Direction</th>
            <th>Open UTC</th>
            <th>Prices</th>
            <th>Lots</th>
            <th>EA</th>
            <th>Classification</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={7}>Sin posiciones abiertas limpias registradas.</td>
            </tr>
          )}

          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${row.position_id}-${index}`}>
              <td className="strong">{row.symbol}</td>
              <td>{row.direction ?? '—'}</td>
              <td>{formatDate(row.open_time)}</td>
              <td><PriceStack trade={row} /></td>
              <td>{formatNumber(row.lots, 2)}</td>
              <td>{row.ea_version ?? '—'}</td>
              <td>
                <Badge tone="ok">{row.ledger_classification ?? 'clean'}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CleanEdgeTable({ rows }: { rows: Trade[] }) {
  return (
    <div className="table-wrap">
      <table className="table-compact">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>State</th>
            <th>Prices</th>
            <th>Lots</th>
            <th>PNL</th>
            <th>EA</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={7}>Sin trades limpios registrados.</td>
            </tr>
          )}

          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${row.position_id}-${index}`}>
              <td className="strong">{row.symbol}</td>
              <td>
                <div className="stack">
                  <span>{row.direction ?? '—'}</span>
                  <span>{row.close_time ? 'closed' : 'open'}</span>
                </div>
              </td>
              <td><PriceStack trade={row} /></td>
              <td>{formatNumber(row.lots, 2)}</td>
              <td>{formatNumber(row.pnl, 2)}</td>
              <td>{row.ea_version ?? '—'}</td>
              <td className="notes-cell">
                <div className="stack">
                  <Badge tone="ok">{row.ledger_classification ?? 'clean'}</Badge>
                  <span>{row.data_quality_notes ?? '—'}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ExcludedTradesTable({ rows }: { rows: Trade[] }) {
  return (
    <div className="table-wrap">
      <table className="table-compact">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>EA</th>
            <th>Classification</th>
            <th>Reason</th>
            <th>PNL</th>
            <th>Dates</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={6}>Sin trades excluidos registrados.</td>
            </tr>
          )}

          {rows.map((row, index) => (
            <tr key={`${row.symbol}-${row.position_id}-${index}`}>
              <td className="strong">{row.symbol}</td>
              <td>{row.ea_version ?? '—'}</td>
              <td><Badge tone="warn">{row.ledger_classification ?? 'excluded'}</Badge></td>
              <td className="notes-cell">{row.close_reason ?? row.event_type ?? '—'}</td>
              <td>{formatNumber(row.pnl, 2)}</td>
              <td>
                <div className="stack">
                  <span>Open {formatDate(row.open_time)}</span>
                  <span>Close {formatDate(row.close_time)}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SignalsTable({
  rows,
  empty,
  showEra = false,
  cutoff,
}: {
  rows: SignalEval[]
  empty: string
  showEra?: boolean
  cutoff?: string
}) {
  return (
    <div className="table-wrap">
      <table className="table-compact">
        <thead>
          <tr>
            <th>Created</th>
            <th>Symbol</th>
            <th>Action</th>
            <th>Direction</th>
            <th>Context</th>
            <th>Raw</th>
            {showEra && <th>Era</th>}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={showEra ? 7 : 6}>{empty}</td>
            </tr>
          )}

          {rows.map((row, index) => {
            const isPrePatch = cutoff ? row.created_at < cutoff : true

            return (
              <tr key={`${row.symbol}-${row.created_at}-${index}`}>
                <td>{formatDate(row.created_at)}</td>
                <td className="strong">{row.symbol}</td>
                <td className="notes-cell">
                  <div className="stack">
                    <span>{row.action ?? '—'}</span>
                    <span>{row.block_reason ?? ''}</span>
                  </div>
                </td>
                <td>{row.direction ?? '—'}</td>
                <td>
                  <div className="stack">
                    <span>Session {row.session ?? '—'}</span>
                    <span>Trend {row.trend_state ?? '—'}</span>
                    <span>Vol {row.volatility_state ?? '—'}</span>
                  </div>
                </td>
                <td>
                  <span className={statusClass(row.raw_payload != null)}>
                    {row.raw_payload != null ? 'OK' : 'NULL'}
                  </span>
                </td>
                {showEra && (
                  <td>
                    <Badge tone={isPrePatch ? 'warn' : 'ok'}>
                      {isPrePatch ? 'pre-patch' : 'post-patch'}
                    </Badge>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function App() {
  const health = useApi<{ ok: boolean; ts: string; service: string; mode: string }>('/api/health')
  const openPositions = useApi<ApiRows<Trade>>('/api/open-positions')
  const cleanEdgeTrades = useApi<ApiRows<Trade>>('/api/clean-edge-trades')
  const excludedTrades = useApi<ApiRows<Trade>>('/api/excluded-trades')
  const latestSignals = useApi<ApiRows<SignalEval>>('/api/latest-signals')
  const liveValidationSignals = useApi<ApiRows<SignalEval>>('/api/live-validation-signals')
  const quality = useApi<DataQualityResponse>('/api/data-quality')

  const openRows = openPositions.data?.rows ?? []
  const cleanRows = cleanEdgeTrades.data?.rows ?? []
  const excludedRows = excludedTrades.data?.rows ?? []
  const signalRows = latestSignals.data?.rows ?? []
  const liveSignalRows = liveValidationSignals.data?.rows ?? []
  const qualitySummary = quality.data?.summary

  const bugDataStatus = useMemo(() => {
    if (!qualitySummary) return 'Waiting'
    if (qualitySummary.live_signal_evals_checked === 0 && qualitySummary.live_trades_checked === 0) {
      return 'Waiting H4'
    }

    const ok =
      qualitySummary.live_incomplete_signal_evals === 0 &&
      qualitySummary.live_incomplete_trade_opens === 0 &&
      qualitySummary.live_incomplete_trade_closes === 0

    return ok ? 'Live OK' : 'Needs Review'
  }, [qualitySummary])

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Algo Trading MT5</p>
        <h1>F5A Operations Dashboard</h1>
        <p className="subtitle">
          Dashboard read-only para monitorear ejecución, muestra limpia, histórico excluido y
          validación live de BUG-DATA-01 sin afectar al EA.
        </p>
      </section>

      <section className="grid">
        <article className="card">
          <p className="card-title">Dashboard API</p>
          <h2 className={statusClass(!health.error && !health.loading)}>
            {health.loading ? 'Checking' : health.error ? 'Fail' : 'OK'}
          </h2>
          <p>{health.data?.service ?? health.error ?? 'Read-only API'}</p>
        </article>

        <article className="card">
          <p className="card-title">Open Positions</p>
          <h2>{openPositions.loading ? '—' : openRows.length}</h2>
          <p>{openRows.length === 1 ? 'posición abierta limpia' : 'posiciones abiertas limpias'}</p>
        </article>

        <article className="card">
          <p className="card-title">Clean Edge Sample</p>
          <h2>{cleanEdgeTrades.loading ? '—' : cleanRows.length}</h2>
          <p>Trades no excluidos para futura evaluación, sin calcular edge todavía.</p>
        </article>

        <article className="card">
          <p className="card-title">BUG-DATA-01</p>
          <h2 className={statusClass(bugDataStatus === 'Live OK')}>
            {quality.loading ? 'Checking' : quality.error ? 'Fail' : bugDataStatus}
          </h2>
          <p>
            {qualitySummary
              ? `${qualitySummary.live_signal_evals_checked} señales live desde cutoff`
              : quality.error ?? 'Esperando próxima validación H4'}
          </p>
        </article>
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <p className="eyebrow">Live state</p>
            <h2>Open Positions</h2>
          </div>
          <Badge tone="ok">clean sample only</Badge>
        </div>
        <OpenPositionsTable rows={openRows} />
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <p className="eyebrow">BUG-DATA-01</p>
            <h2>Live Validation Window</h2>
          </div>
          <Badge tone={qualitySummary?.latest_signal_is_pre_bug_data_01 ? 'warn' : 'ok'}>
            {qualitySummary?.latest_signal_is_pre_bug_data_01 ? 'waiting next H4' : 'post-patch signal seen'}
          </Badge>
        </div>

        <div className="quality-grid">
          <div className="metric">
            <span>Cutoff</span>
            <strong>{quality.data?.cutoff ? formatDate(quality.data.cutoff) : '—'}</strong>
          </div>
          <div className="metric">
            <span>Live signal evals</span>
            <strong>{qualitySummary?.live_signal_evals_checked ?? '—'}</strong>
          </div>
          <div className="metric">
            <span>Incomplete live signals</span>
            <strong>{qualitySummary?.live_incomplete_signal_evals ?? '—'}</strong>
          </div>
          <div className="metric">
            <span>Live trades checked</span>
            <strong>{qualitySummary?.live_trades_checked ?? '—'}</strong>
          </div>
          <div className="metric">
            <span>Incomplete opens</span>
            <strong>{qualitySummary?.live_incomplete_trade_opens ?? '—'}</strong>
          </div>
          <div className="metric">
            <span>Incomplete closes</span>
            <strong>{qualitySummary?.live_incomplete_trade_closes ?? '—'}</strong>
          </div>
        </div>

        <div className="notice">
          <strong>Lectura actual:</strong>{' '}
          {qualitySummary?.latest_signal_is_pre_bug_data_01
            ? 'La última señal disponible es anterior al patch BUG-DATA-01; no debe evaluarse como fallo live.'
            : 'Ya existe al menos una señal posterior al patch BUG-DATA-01.'}
        </div>
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <p className="eyebrow">Clean ledger</p>
            <h2>Clean Edge Sample</h2>
          </div>
          <Badge tone="neutral">no PF / no WR yet</Badge>
        </div>
        <CleanEdgeTable rows={cleanRows} />
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <p className="eyebrow">Audit</p>
            <h2>Excluded / Legacy / Incident Trades</h2>
          </div>
          <Badge tone="warn">excluded from edge</Badge>
        </div>
        <ExcludedTradesTable rows={excludedRows} />
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <p className="eyebrow">Post-patch</p>
            <h2>Live Validation Signals</h2>
          </div>
          <Badge tone={liveSignalRows.length > 0 ? 'ok' : 'warn'}>
            {liveSignalRows.length > 0 ? 'live data present' : 'waiting'}
          </Badge>
        </div>
        <SignalsTable
          rows={liveSignalRows}
          empty="Sin señales posteriores al cutoff BUG-DATA-01. Esperando próximo ciclo H4."
        />
      </section>

      <section className="section">
        <div className="section-header">
          <div>
            <p className="eyebrow">Historical context</p>
            <h2>Latest Signals Before / Across Patch</h2>
          </div>
          <Badge tone="neutral">audit only</Badge>
        </div>
        <SignalsTable
          rows={signalRows.slice(0, 16)}
          empty="Sin señales registradas."
          showEra
          cutoff={quality.data?.cutoff}
        />
      </section>
    </main>
  )
}

export default App
