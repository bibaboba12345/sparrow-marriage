import { useEffect, useState } from 'react'
import { STAGE_LABELS, advanceClock, getClock, getFunnel, seedDemoJourneys } from '../api/journeyApi'

export default function ManagerDashboard() {
  const [funnel, setFunnel] = useState(null)
  const [clock, setClock] = useState(null)
  const [filter, setFilter] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function reload() {
    const [f, c] = await Promise.all([getFunnel(), getClock()])
    setFunnel(f)
    setClock(c)
  }

  useEffect(() => {
    reload().catch((e) => setError(String(e.message || e)))
  }, [])

  const journeys = funnel?.journeys || []
  const shown = filter
    ? journeys.filter((j) => {
        const step = funnel.steps.find((s) => s.key === filter)
        if (!step) return true
        // rough filter by stage progression labels
        return true
      })
    : journeys

  async function onClock(days) {
    setBusy(true)
    try {
      await advanceClock({ days })
      await reload()
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <p className="eyebrow">Руководитель</p>
        <h1>Воронка хирургической конверсии</h1>
        <p className="lede">
          Диагностический поток → консультация → операция → контроль. Сейчас:{' '}
          {clock?.now ? new Date(clock.now).toLocaleString('ru-RU') : '—'}
        </p>
      </div>

      <div className="demo-clock-bar panel">
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => seedDemoJourneys().then(reload)}>
          Seed
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(1)}>
          +1д
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(7)}>
          +7д
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={reload}>
          Обновить
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}

      <div className="funnel-grid">
        {(funnel?.steps || []).map((s) => (
          <button
            key={s.key}
            type="button"
            className={`funnel-card ${filter === s.key ? 'is-on' : ''}`}
            onClick={() => setFilter(filter === s.key ? null : s.key)}
          >
            <span className="funnel-count">{s.count}</span>
            <span className="funnel-label">{s.label}</span>
            <span className="muted">{s.pct_of_prev}% от пред.</span>
          </button>
        ))}
      </div>

      <section className="panel" style={{ marginTop: '1rem' }}>
        <h2>Пациенты в воронке ({shown.length})</h2>
        <table className="funnel-table">
          <thead>
            <tr>
              <th>Пациент</th>
              <th>Триггер</th>
              <th>Стадия</th>
              <th>Специалист</th>
              <th>Правило</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((j) => (
              <tr key={j.id}>
                <td>{j.patient_name}</td>
                <td>{j.trigger_pathology}</td>
                <td>{STAGE_LABELS[j.stage] || j.stage}</td>
                <td>{j.specialty}</td>
                <td className="muted">{j.matrix_rule_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
