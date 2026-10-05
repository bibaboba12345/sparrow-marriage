import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  STAGE_LABELS,
  advanceClock,
  bookJourney,
  getClock,
  getJourney,
  listJourneys,
  listNotifications,
  listSlots,
  markNotificationRead,
  patientResponse,
  seedDemoJourneys,
} from '../api/journeyApi'

function formatWhen(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function PatientDashboard() {
  const { user } = useAuth()
  const patientId = user?.id
  const [journeys, setJourneys] = useState([])
  const [notifications, setNotifications] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [slots, setSlots] = useState([])
  const [notifOpen, setNotifOpen] = useState(false)
  const [clock, setClock] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  async function reload() {
    if (!patientId) return
    const [js, ns, cl] = await Promise.all([
      listJourneys({ patientId }),
      listNotifications(patientId),
      getClock(),
    ])
    setJourneys(js)
    setNotifications(ns)
    setClock(cl)
    if (!selectedId && js[0]) setSelectedId(js[0].id)
  }

  useEffect(() => {
    reload().catch((e) => setError(String(e.message || e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    getJourney(selectedId)
      .then(setDetail)
      .catch((e) => setError(String(e.message || e)))
  }, [selectedId])

  const unread = useMemo(
    () => notifications.filter((n) => !n.read && n.channel === 'cabinet').length,
    [notifications],
  )
  const cabinetNotifs = useMemo(
    () => notifications.filter((n) => n.channel === 'cabinet'),
    [notifications],
  )

  async function openBook() {
    if (!detail) return
    setBusy(true)
    setError('')
    try {
      const res = await listSlots(detail.slot_profile || 'operating_gyn', detail.id)
      setSlots(res.slots || [])
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function onBook(slot) {
    setBusy(true)
    try {
      await bookJourney(detail.id, slot)
      setToast('Вы записаны')
      setSlots([])
      await reload()
      setDetail(await getJourney(detail.id))
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function onNotifClick(n) {
    if (!n.read) await markNotificationRead(n.id)
    if (n.journey_id) setSelectedId(n.journey_id)
    setNotifications((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)))
    if ((n.actions || []).includes('book')) openBook()
  }

  async function onPatientAction(action) {
    if (!detail) return
    if (action === 'book') {
      await openBook()
      return
    }
    setBusy(true)
    try {
      await patientResponse(detail.id, action)
      await reload()
      setDetail(await getJourney(detail.id))
      setToast(action === 'already_seen' ? 'Отмечено' : 'Маршрут обновлён')
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function onClock(hours, days = 0) {
    setBusy(true)
    try {
      const res = await advanceClock({ hours, days })
      setClock(res)
      setToast(`Модельное время +${hours || days * 24}ч · эскалаций: ${(res.escalations_fired || []).length}`)
      await reload()
      if (selectedId) setDetail(await getJourney(selectedId))
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function onSeed() {
    setBusy(true)
    try {
      await seedDemoJourneys()
      await reload()
      setToast('Demo seed загружен')
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="patient-dash">
      <header className="patient-dash-head">
        <div>
          <p className="eyebrow">Кабинет пациента</p>
          <h1>{user?.name || 'Пациент'}</h1>
          <p className="lede patient-dash-meta">
            Маршруты по результатам УЗИ · модельные часы:{' '}
            {clock?.now ? formatWhen(clock.now) : '—'}
          </p>
        </div>

        <div className="notif-wrap">
          <button
            type="button"
            className={`notif-bell ${unread ? 'has-unread' : ''}`}
            aria-label="Уведомления"
            onClick={() => setNotifOpen((v) => !v)}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="currentColor"
                d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm6-6V11a6 6 0 1 0-12 0v5l-2 2v1h16v-1l-2-2Z"
              />
            </svg>
            {unread > 0 ? <span className="notif-badge">{unread}</span> : null}
          </button>
          {notifOpen ? (
            <div className="notif-panel" role="dialog">
              <div className="notif-panel-head">
                <strong>Уведомления</strong>
                <span className="muted">{cabinetNotifs.length}</span>
              </div>
              <ul className="notif-list">
                {cabinetNotifs.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      className={`notif-item level-${n.level} ${n.read ? 'is-read' : ''}`}
                      onClick={() => onNotifClick(n)}
                    >
                      <div className="notif-item-top">
                        <span className={`notif-tag level-${n.level}`}>{n.title}</span>
                        <time className="muted">{formatWhen(n.sent_at || n.created_at)}</time>
                      </div>
                      <p>{n.text}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </header>

      {notifOpen ? (
        <button type="button" className="notif-backdrop" aria-label="Закрыть" onClick={() => setNotifOpen(false)} />
      ) : null}

      <div className="demo-clock-bar panel">
        <strong>Демо-время</strong>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(24)}>
          +24ч
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(72)}>
          +72ч
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(0, 7)}>
          +7д
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(0, 14)}>
          +14д
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={() => onClock(0, 30)}>
          +30д
        </button>
        <button type="button" className="btn ghost tiny" disabled={busy} onClick={onSeed}>
          Seed demo
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {toast ? <p className="toast-inline">{toast}</p> : null}

      <div className="patient-grid">
        <section className="panel patient-panel">
          <h2>Мои маршруты</h2>
          {journeys.length === 0 ? (
            <p className="empty">
              Пока нет маршрутов. Нажмите «Seed demo» или дождитесь протокола из админки.
            </p>
          ) : (
            <ul className="protocol-pick">
              {journeys.map((j) => (
                <li key={j.id}>
                  <button
                    type="button"
                    className={`protocol-pick-btn ${selectedId === j.id ? 'is-active' : ''}`}
                    onClick={() => setSelectedId(j.id)}
                  >
                    <span className="protocol-pick-title">{j.trigger_pathology}</span>
                    <span className="muted">{j.source_study}</span>
                    <span className="sev-dot sev-suspicious">{STAGE_LABELS[j.stage] || j.stage}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel patient-panel">
          <h2>Карточка маршрута</h2>
          {!detail ? (
            <p className="empty">Выберите маршрут</p>
          ) : (
            <article className="protocol-detail">
              <header>
                <h3>{detail.trigger_pathology}</h3>
                <p className="muted">
                  {detail.source_study} · {STAGE_LABELS[detail.stage] || detail.stage} ·{' '}
                  {detail.specialty}
                </p>
              </header>
              <p className="rec-quote">{detail.evidence?.patient_message || 'Рекомендована консультация специалиста.'}</p>

              <div className="chip-row" style={{ marginTop: '0.75rem' }}>
                <button type="button" className="btn primary" disabled={busy} onClick={openBook}>
                  Записаться
                </button>
                <button type="button" className="btn ghost" disabled={busy} onClick={() => onPatientAction('already_seen')}>
                  Уже обратился
                </button>
                <button type="button" className="btn ghost" disabled={busy} onClick={() => onPatientAction('decline')}>
                  Не планирую
                </button>
              </div>

              {slots.length > 0 ? (
                <div className="slots-block">
                  <h4>Ближайшие консультации по вашему результату УЗИ</h4>
                  <ul className="slot-list">
                    {slots.map((s) => (
                      <li key={s.id}>
                        <button type="button" className="slot-btn" disabled={busy} onClick={() => onBook(s)}>
                          <strong>{formatWhen(s.starts_at)}</strong>
                          <span>
                            {s.modality === 'online' ? 'онлайн' : s.location} · {s.doctor}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {detail.appointments?.length ? (
                <div style={{ marginTop: '1rem' }}>
                  <h4>Записи</h4>
                  <ul className="record-list">
                    {detail.appointments.map((a) => (
                      <li key={a.id} className="record-row">
                        <strong>
                          {formatWhen(a.starts_at)} · {a.doctor}
                        </strong>
                        <p className="muted">
                          {a.location} · {a.state} · {a.kind}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </article>
          )}
        </section>
      </div>
    </div>
  )
}
