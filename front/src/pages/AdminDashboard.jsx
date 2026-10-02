import { useEffect, useState } from 'react'
import { listRoutes, saveRoute } from '../api/stubApi'
import PriorityBadge from '../components/PriorityBadge'
import RouteCard from '../components/RouteCard'

export default function AdminDashboard() {
  const [routes, setRoutes] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      const data = await listRoutes()
      if (!alive) return
      setRoutes(data)
      setSelectedId(data[0]?.id ?? null)
      setDraft(data[0] ? { ...data[0] } : null)
      setLoading(false)
    })()
    return () => {
      alive = false
    }
  }, [])

  function select(id) {
    const item = routes.find((r) => r.id === id)
    setSelectedId(id)
    setDraft(item ? { ...item } : null)
    setToast('')
  }

  async function handleSave(route) {
    setSaving(true)
    const saved = await saveRoute(route)
    setRoutes((prev) => prev.map((r) => (r.id === saved.id ? saved : r)))
    setDraft(saved)
    setToast(`Сохранено локально · ${saved.savedAt}`)
    setSaving(false)
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Admin-дашборд</h1>
        <p className="lede">Обзор решений и ручная корректировка (Human-in-the-loop).</p>
      </header>

      {loading ? (
        <p className="muted">Загрузка stub-списка…</p>
      ) : (
        <div className="split admin-split">
          <section className="panel list-panel">
            <h2>Очередь маршрутов</h2>
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
                      {r.department} · {r.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel">
            <h2>Редактирование решения</h2>
            {draft ? (
              <>
                <RouteCard
                  route={draft}
                  editable
                  onChange={setDraft}
                  onSave={handleSave}
                  saving={saving}
                />
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
