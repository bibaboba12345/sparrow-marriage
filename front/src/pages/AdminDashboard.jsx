import { useCallback, useEffect, useState } from 'react'
import {
  approveRoute,
  deleteRoute,
  listPatients,
  listRoutes,
  saveRoute,
} from '../api/routesApi'
import PriorityBadge from '../components/PriorityBadge'
import RouteCard from '../components/RouteCard'

const APPROVED_FILTERS = [
  { value: 'pending', label: 'Очередь (неаппрувнутые)', approved: false },
  { value: 'approved', label: 'Только approved', approved: true },
  { value: 'all', label: 'Все записи', approved: undefined },
]

export default function AdminDashboard() {
  const [routes, setRoutes] = useState([])
  const [patients, setPatients] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [patientFilter, setPatientFilter] = useState('')
  const [approvedFilter, setApprovedFilter] = useState('pending')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const filterMeta = APPROVED_FILTERS.find((f) => f.value === approvedFilter)
      const [data, pats] = await Promise.all([
        listRoutes({
          patientId: patientFilter || undefined,
          approved: filterMeta?.approved,
        }),
        listPatients(),
      ])
      setPatients(pats)
      setRoutes(data)
      setSelectedId((prev) => {
        if (prev && data.some((r) => r.id === prev)) return prev
        return data[0]?.id ?? null
      })
      setDraft((prev) => {
        const nextId = prev && data.some((r) => r.id === prev.id) ? prev.id : data[0]?.id
        const item = data.find((r) => r.id === nextId)
        return item ? { ...item } : null
      })
    } catch (err) {
      setError(`Не удалось загрузить очередь: ${err.message || err}`)
    } finally {
      setLoading(false)
    }
  }, [patientFilter, approvedFilter])

  useEffect(() => {
    load()
  }, [load])

  function select(id) {
    const item = routes.find((r) => r.id === id)
    setSelectedId(id)
    setDraft(item ? { ...item } : null)
    setToast('')
  }

  async function handleSave(route) {
    setBusy(true)
    setToast('')
    try {
      const saved = await saveRoute(route)
      setToast(`Сохранено · approved сброшен · ${saved.updatedAt}`)
      await load()
      setSelectedId(saved.id)
      setDraft({ ...saved })
    } catch (err) {
      setToast(`Ошибка сохранения: ${err.message || err}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleApprove() {
    if (!draft) return
    setBusy(true)
    setToast('')
    try {
      const saved = await approveRoute(draft.id)
      setToast(`APPROVE · ${saved.id}`)
      await load()
      setSelectedId(saved.id)
      setDraft({ ...saved })
    } catch (err) {
      setToast(`Ошибка approve: ${err.message || err}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!draft) return
    if (!window.confirm(`Удалить запись ${draft.id}?`)) return
    setBusy(true)
    setToast('')
    try {
      await deleteRoute(draft.id)
      setToast(`Удалено · ${draft.id}`)
      await load()
    } catch (err) {
      setToast(`Ошибка удаления: ${err.message || err}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Admin-дашборд</h1>
        <p className="lede">Очередь на проверку · APPROVE / DELETE · фильтры по юзеру и approved.</p>
      </header>

      <section className="panel filters-bar">
        <label className="field">
          <span>Юзер (patient_id)</span>
          <select value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)}>
            <option value="">Все юзеры</option>
            {patients.map((p) => (
              <option key={p.patientId} value={p.patientId}>
                {p.patientName} ({p.patientId})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Статус проверки</span>
          <select value={approvedFilter} onChange={(e) => setApprovedFilter(e.target.value)}>
            {APPROVED_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn ghost" disabled={loading || busy} onClick={load}>
          Обновить
        </button>
      </section>

      {loading ? (
        <p className="muted">Загрузка очереди…</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : (
        <div className="split admin-split">
          <section className="panel list-panel">
            <h2>
              {approvedFilter === 'pending' ? 'Очередь на проверку' : 'Маршруты'} ({routes.length})
            </h2>
            {routes.length === 0 ? (
              <p className="empty">Нет записей по фильтру</p>
            ) : (
              <ul className="route-list">
                {routes.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      className={`route-list-item ${selectedId === r.id ? 'active' : ''}`}
                      onClick={() => select(r.id)}
                    >
                      <div className="route-list-top">
                        <strong>{r.patientName}</strong>
                        <PriorityBadge priority={r.priority} />
                      </div>
                    <span className="muted">
                      {r.patientId} · {(r.documents || []).length} док. ·{' '}
                      {r.approved ? 'approved' : 'pending'}
                    </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel">
            <h2>Карточка</h2>
            {draft ? (
              <>
                <p className="hint" style={{ marginBottom: '0.75rem' }}>
                  {draft.approved ? (
                    <span className="pill">approved</span>
                  ) : (
                    <span className="pill pill-warn">ожидает проверки</span>
                  )}{' '}
                  · {draft.patientId}
                </p>
                <RouteCard
                  route={draft}
                  editable
                  onChange={setDraft}
                  onSave={handleSave}
                  saving={busy}
                />
                <div className="actions admin-actions">
                  <button
                    type="button"
                    className="btn approve"
                    disabled={busy || draft.approved}
                    onClick={handleApprove}
                  >
                    APPROVE
                  </button>
                  <button type="button" className="btn danger" disabled={busy} onClick={handleDelete}>
                    Удалить
                  </button>
                </div>
                {toast && <p className="hint">{toast}</p>}
              </>
            ) : (
              <p className="empty">Выберите карточку слева</p>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
