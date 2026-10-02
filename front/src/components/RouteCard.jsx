import PriorityBadge from './PriorityBadge'

export default function RouteCard({ route, editable = false, onChange, onSave, saving }) {
  const value = route

  function patch(field, next) {
    if (!editable || !onChange) return
    onChange({ ...value, [field]: next })
  }

  function patchList(field, text) {
    patch(
      field,
      text
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    )
  }

  return (
    <article className="route-panel">
      <div className="route-head">
        <div>
          <h2>{value.patientName}</h2>
          <p className="muted">
            {value.id}
            {value.age != null ? ` · ${value.age} лет` : ''}
            {value.sourceFile ? ` · ${value.sourceFile}` : ''}
          </p>
        </div>
        <PriorityBadge priority={value.priority} />
      </div>

      <div className="route-grid">
        <label className="field">
          <span>Приоритет</span>
          {editable ? (
            <select value={value.priority} onChange={(e) => patch('priority', e.target.value)}>
              <option value="emergency">Экстренное</option>
              <option value="urgent">Срочное</option>
              <option value="routine">Плановое</option>
            </select>
          ) : (
            <strong>{PRIORITY_LABEL(value.priority)}</strong>
          )}
        </label>

        <label className="field">
          <span>Отделение</span>
          {editable ? (
            <input value={value.department} onChange={(e) => patch('department', e.target.value)} />
          ) : (
            <strong>{value.department}</strong>
          )}
        </label>

        <label className="field">
          <span>Специалисты</span>
          {editable ? (
            <input
              value={value.specialists.join(', ')}
              onChange={(e) => patchList('specialists', e.target.value)}
            />
          ) : (
            <strong>{value.specialists.join(', ') || '—'}</strong>
          )}
        </label>

        <label className="field">
          <span>Анализы / исследования</span>
          {editable ? (
            <input
              value={value.requiredTests.join(', ')}
              onChange={(e) => patchList('requiredTests', e.target.value)}
            />
          ) : (
            <strong>{value.requiredTests.join(', ') || '—'}</strong>
          )}
        </label>
      </div>

      <section className="reasoning">
        <h3>Clinical Reasoning</h3>
        <ul>
          {(value.reasoning || []).map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </section>

      {editable && (
        <div className="actions">
          <button type="button" className="btn primary" disabled={saving} onClick={() => onSave?.(value)}>
            {saving ? 'Сохранение…' : 'Сохранить правки (stub)'}
          </button>
          <span className="hint">Human-in-the-loop · изменения только в UI</span>
        </div>
      )}
    </article>
  )
}

function PRIORITY_LABEL(key) {
  return { emergency: 'Экстренное', urgent: 'Срочное', routine: 'Плановое' }[key] || key
}
