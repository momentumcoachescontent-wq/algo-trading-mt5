import './App.css'

const cards = [
  {
    title: 'Trading Worker',
    value: 'Protected',
    detail: 'Webhook operativo separado de este dashboard.',
  },
  {
    title: 'BUG-DATA-01',
    value: 'Monitoring',
    detail: 'Pendiente validar signal_evals y trades en próximo ciclo H4.',
  },
  {
    title: 'Mode',
    value: 'Read-only',
    detail: 'Este sitio no ejecuta trades ni modifica parámetros.',
  },
  {
    title: 'Phase',
    value: 'F5A Protection / Ledger',
    detail: 'Sin optimización, sin outcome_linker --write.',
  },
]

function App() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Algo Trading MT5</p>
        <h1>F5A Operations Dashboard</h1>
        <p className="subtitle">
          Capa inicial de observabilidad para monitorear salud operativa, persistencia de datos
          y estado del ledger sin afectar la ejecución del EA.
        </p>
      </section>

      <section className="grid">
        {cards.map((card) => (
          <article className="card" key={card.title}>
            <p className="card-title">{card.title}</p>
            <h2>{card.value}</h2>
            <p>{card.detail}</p>
          </article>
        ))}
      </section>

      <section className="panel">
        <h2>Current validation gate</h2>
        <ul>
          <li>Worker trading separado y operativo.</li>
          <li>Webhook protegido por X-EA-Secret.</li>
          <li>Próxima validación: signal_evals con raw_payload y contexto H4 completo.</li>
          <li>Próxima validación: trade_open/trade_close con precios, lotes, PnL y close_reason.</li>
        </ul>
      </section>
    </main>
  )
}

export default App
