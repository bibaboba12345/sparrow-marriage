import { useEffect, useState } from 'react'
import {
  STAGE_LABELS,
  TACTICS_OPTIONS,
  appointmentOutcome,
  getJourney,
  listJourneys,
  setTactics,
} from '../api/journeyApi'

export default function DoctorDashboard() {
  const [journeys, setJourneys] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [tactics, setTacticsLocal] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [patientLookup, setPatientLookup] = useState('pat-ivanova')

  async function reload() {
    const rows = await listJourneys({ status: 'active' })
    setJourneys(rows)
  }

  useEffect(() => {
    reload().catch((e) => setError(String(e.message || e)))
  }, [])

  useEffect(() => {
    if (!selectedId) return
    getJourney(selectedId)
      .then((d) => {
        setDetail(d)
        setTacticsLocal(d.tactics || '')
      })
      .catch((e) => setError(String(e.message || e)))
  }, [selectedId])

  const openForVisit = journeys.filter((j) =>
    ['booked', 'visit_done', 'notified', 'needs_rebook', 'no_show'].includes(j.stage),
  )
  const unfinished = journeys.filter(
    (j) => j.patient_id === patientLookup && !['completed', 'cancelled', 'abandoned'].includes(j.status),
  )

  async function completeVisit() {
    if (!detail) return
    if (!tactics) {
      setError('Выберите тактику — завершить приём без маршрута нельзя')
      return
    }
    setBusy(true)
    setError('')
    try {
      if (detail.stage === 'booked') {
        await appointmentOutcome(detail.id, 'completed')
      }
      await setTactics(detail.id, tactics)
      setToast('Приём завершён, тактика сохранена')
      await reload()
      setDetail(await getJourney(detail.id))
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function markNoShow() {
    if (!detail) return
    setBusy(true)
    try {
      await appointmentOutcome(detail.id, 'no_show')
      setToast('Неявка зафиксирована')
      await reload()
      setDetail(await getJourney(detail.id))
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mis-page">
      <div className="page-head">
        <p className="eyebrow">МИС · прототип формы 1С</p>
        <h1>Приём врача</h1>
        <p className="lede">Баннер маршрута и обязательный выбор тактики при завершении.</p>
      </div>

      <div className="panel" style={{ marginBottom: '1rem' }}>
        <label className="field">
          <span>Карточка пациента (проверка незавершённого маршрута)</span>
          <input value={patientLookup} onChange={(e) => setPatientLookup(e.target.value)} />
        </label>
        {unfinished.length > 0 ? (
          <div className="mis-banner is-warn">
            <strong>Незавершённый клинический маршрут</strong>
            {unfinished.map((j) => (
              <p key={j.id}>
                {j.detected_at?.slice(0, 10)}: {j.source_study} — {j.trigger_pathology}. Стадия:{' '}
                {STAGE_LABELS[j.stage] || j.stage}. Консультация в системе{' '}
                {['visit_done', 'tactics_chosen', 'referral_created'].includes(j.stage)
                  ? 'зафиксирована'
                  : 'не зафиксирована'}
                .
              </p>
            ))}
          </div>
        ) : (
          <p className="muted">Незавершённых маршрутов для {patientLookup} нет.</p>
        )}
      </div>

      <div className="patient-grid">
        <section className="panel">
          <h2>Пациенты в маршруте</h2>
          <ul className="protocol-pick">
            {openForVisit.map((j) => (
              <li key={j.id}>
                <button
                  type="button"
                  className={`protocol-pick-btn ${selectedId === j.id ? 'is-active' : ''}`}
                  onClick={() => setSelectedId(j.id)}
                >
                  <span className="protocol-pick-title">{j.patient_name}</span>
                  <span className="muted">{j.trigger_pathology}</span>
                  <span className="sev-dot sev-suspicious">{STAGE_LABELS[j.stage]}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Документ приёма</h2>
          {!detail ? (
            <p className="empty">Выберите пациента</p>
          ) : (
            <>
              <div className="mis-banner is-info">
                <strong>Пациент включён в диагностический маршрут</strong>
                <p>
                  Основание: {detail.source_study}
                  {detail.detected_at ? ` от ${detail.detected_at.slice(0, 10)}` : ''} — признаки «
                  {detail.trigger_pathology}». Требуется определить дальнейшую тактику.
                </p>
                <p className="muted">
                  Правило {detail.matrix_rule_id} · v{detail.matrix_version} · {detail.clinic}
                </p>
              </div>

              <h3>Тактика (обязательно)</h3>
              <div className="tactics-grid">
                {TACTICS_OPTIONS.map((t) => (
                  <label key={t.id} className={`tactics-option ${tactics === t.id ? 'is-on' : ''}`}>
                    <input
                      type="radio"
                      name="tactics"
                      value={t.id}
                      checked={tactics === t.id}
                      onChange={() => setTacticsLocal(t.id)}
                    />
                    {t.label}
                  </label>
                ))}
              </div>

              {error ? <p className="error">{error}</p> : null}
              {toast ? <p className="toast-inline">{toast}</p> : null}

              <div className="chip-row" style={{ marginTop: '1rem' }}>
                <button type="button" className="btn primary" disabled={busy || !tactics} onClick={completeVisit}>
                  Завершить приём
                </button>
                <button type="button" className="btn ghost" disabled={busy} onClick={markNoShow}>
                  Неявка
                </button>
              </div>
              {!tactics ? (
                <p className="muted">Кнопка «Завершить приём» недоступна без выбора тактики.</p>
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
