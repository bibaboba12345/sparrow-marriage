import PriorityBadge from './PriorityBadge'
import DocumentsPanel from './DocumentsPanel'

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

  const docCount = value.documents?.length || 0
  const decision = value.decisionJson || {}
  const vectorActive = decision.vector_active || decision.query_active || []
  const textTokens = decision.text_tokens || []
  const matchedPhrases = decision.matched_phrases || []
  const tokenFilter = decision.token_filter || {}
  const dropped = tokenFilter.dropped || []

  return (
    <article className="route-panel">
      <div className="route-head">
        <div>
          <h2>{value.patientName}</h2>
          <p className="muted">
            {value.id}
            {value.patientId ? ` · ${value.patientId}` : ''}
            {value.age != null ? ` · ${value.age} лет` : ''}
            {docCount ? ` · ${docCount} док.` : ''}
            {value.approved != null ? ` · ${value.approved ? 'approved' : 'pending'}` : ''}
          </p>
        </div>
        <PriorityBadge priority={value.priority} />
      </div>

      {(decision.matched_case_id || vectorActive.length > 0 || textTokens.length > 0) && (
        <section className="match-box">
          <h3>Vector match</h3>
          <p className="muted">
            case <code>{decision.matched_case_id || '—'}</code>
            {decision.matched_case_title ? ` · ${decision.matched_case_title}` : ''}
            {' · '}
            score={decision.match_score ?? '—'}
            {decision.decider_source ? ` · ${decision.decider_source}` : ''}
            {tokenFilter.source ? ` · filter=${tokenFilter.source}` : ''}
          </p>
          {textTokens.length > 0 && (
            <p className="hint">
              Токены: {textTokens.slice(0, 12).join(' · ')}
              {textTokens.length > 12 ? '…' : ''}
            </p>
          )}
          {dropped.length > 0 && (
            <p className="hint">
              Отброшено (норма/отрицание):{' '}
              {dropped
                .slice(0, 8)
                .map((d) => d.token || d.reason)
                .filter(Boolean)
                .join(' · ')}
              {dropped.length > 8 ? '…' : ''}
            </p>
          )}
          {matchedPhrases.length > 0 && (
            <p className="hint">
              Маппинг:{' '}
              {matchedPhrases
                .slice(0, 10)
                .map((m) => `${m.token}→${m.feature}`)
                .join(' · ')}
              {matchedPhrases.length > 10 ? '…' : ''}
            </p>
          )}
          {vectorActive.length > 0 && (
            <div className="chip-row">
              {vectorActive.map((f) => (
                <span key={f} className="chip">
                  {f}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

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

      <section className="docs-section">
        <h3>Documents ({docCount})</h3>
        <DocumentsPanel documents={value.documents || []} />
      </section>

      {editable && (
        <div className="actions">
          <button type="button" className="btn primary" disabled={saving} onClick={() => onSave?.(value)}>
            {saving ? 'Сохранение…' : 'Сохранить в БД'}
          </button>
          <span className="hint">Human-in-the-loop · PATCH /api/v1/routes</span>
        </div>
      )}
    </article>
  )
}

function PRIORITY_LABEL(key) {
  return { emergency: 'Экстренное', urgent: 'Срочное', routine: 'Плановое' }[key] || key
}
