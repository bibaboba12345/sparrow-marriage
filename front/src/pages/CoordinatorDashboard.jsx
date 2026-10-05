import { useEffect, useState } from 'react'
import {
  STAGE_LABELS,
  completeTask,
  listCoordinatorTasks,
  listJourneys,
  setHospitalizationDate,
} from '../api/journeyApi'

export default function CoordinatorDashboard() {
  const [tasks, setTasks] = useState([])
  const [journeys, setJourneys] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  async function reload() {
    const [t, j] = await Promise.all([listCoordinatorTasks('open'), listJourneys({ status: 'active' })])
    setTasks(t)
    setJourneys(j)
  }

  useEffect(() => {
    reload().catch((e) => setError(String(e.message || e)))
  }, [])

  async function onComplete(id) {
    setBusy(true)
    try {
      await completeTask(id)
      setToast('Задача закрыта')
      await reload()
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function onSetHosp(journeyId) {
    setBusy(true)
    try {
      await setHospitalizationDate(journeyId)
      setToast('Дата госпитализации назначена (+3 дня)')
      await reload()
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const needHosp = journeys.filter((j) => j.stage === 'referral_created' && !j.hospitalization_date)

  return (
    <div>
      <div className="page-head">
        <p className="eyebrow">Координатор маршрута</p>
        <h1>Очередь задач</h1>
        <p className="lede">Звонки, госпитализация без даты, эскалации.</p>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {toast ? <p className="toast-inline">{toast}</p> : null}

      {needHosp.length > 0 ? (
        <section className="panel" style={{ marginBottom: '1rem' }}>
          <h2>Без даты госпитализации</h2>
          <ul className="record-list">
            {needHosp.map((j) => (
              <li key={j.id} className="record-row">
                <div>
                  <strong>
                    {j.patient_name} · {j.trigger_pathology}
                  </strong>
                  <p className="muted">{STAGE_LABELS[j.stage]}</p>
                </div>
                <button type="button" className="btn primary" disabled={busy} onClick={() => onSetHosp(j.id)}>
                  Назначить дату
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="panel">
        <h2>Открытые задачи ({tasks.length})</h2>
        {tasks.length === 0 ? (
          <p className="empty">Очередь пуста — сдвиньте демо-время в кабинете пациента.</p>
        ) : (
          <ul className="record-list">
            {tasks.map((t) => (
              <li key={t.id} className="record-row coord-task">
                <div>
                  <strong>
                    [{t.kind}] {t.title}
                  </strong>
                  <p className="muted">journey {t.journey_id}</p>
                  <p className="record-note" style={{ whiteSpace: 'pre-wrap' }}>
                    {t.script}
                  </p>
                </div>
                <button type="button" className="btn ghost" disabled={busy} onClick={() => onComplete(t.id)}>
                  Выполнено
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
