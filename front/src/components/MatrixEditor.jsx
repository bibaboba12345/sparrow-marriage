import { useEffect, useMemo, useState } from 'react'
import {
  getMatrixProfiles,
  getPathologyLabels,
  saveProfileTriggers,
} from '../api/journeyApi'

function labelsToText(arr) {
  return (arr || []).join(', ')
}

function textToLabels(s) {
  return String(s || '')
    .split(/[,;\n]+/)
    .map((x) => x.trim())
    .filter(Boolean)
}

function emptyRule(profile, specialty, study) {
  return {
    id: `${profile}_new_${Date.now().toString(36)}`,
    specialty: specialty || '',
    study: study || '',
    target_days: 7,
    pathology_labels: [],
    token_any: [],
    rads: null,
    patient_message: '',
    _labelsText: '',
    _tokensText: '',
    _radsText: '',
  }
}

function hydrateRule(r) {
  const rads = r.rads
  let radsText = ''
  if (rads?.prefixes?.length) {
    radsText = `${rads.prefixes.join('|')}>=${rads.min ?? 3}`
  }
  return {
    ...r,
    pathology_labels: r.pathology_labels || [],
    token_any: r.token_any || [],
    _labelsText: labelsToText(r.pathology_labels),
    _tokensText: labelsToText(r.token_any),
    _radsText: radsText,
  }
}

function parseRads(text) {
  const t = String(text || '').trim()
  if (!t) return null
  // BI_RADS|O_RADS>=3
  const m = t.match(/^([A-Za-z0-9_|]+)\s*>=\s*(\d+(?:[.,]\d+)?)$/)
  if (!m) return null
  return {
    prefixes: m[1].split('|').map((x) => x.trim()).filter(Boolean),
    min: Number(m[2].replace(',', '.')),
  }
}

export default function MatrixEditor() {
  const [profiles, setProfiles] = useState([])
  const [version, setVersion] = useState('')
  const [activeProfile, setActiveProfile] = useState('')
  const [draft, setDraft] = useState([])
  const [specialty, setSpecialty] = useState('')
  const [study, setStudy] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  async function reload() {
    const [p, labs] = await Promise.all([getMatrixProfiles(), getPathologyLabels()])
    setProfiles(p.profiles || [])
    setVersion(p.version || '')
    setSuggestions(labs.labels || [])
    const first = (p.profiles || [])[0]
    if (first && !activeProfile) {
      selectProfile(first, p.profiles)
    } else if (activeProfile) {
      const cur = (p.profiles || []).find((x) => x.slot_profile === activeProfile)
      if (cur) selectProfile(cur, p.profiles)
    }
  }

  function selectProfile(prof, list = profiles) {
    const p = typeof prof === 'string' ? list.find((x) => x.slot_profile === prof) : prof
    if (!p) return
    setActiveProfile(p.slot_profile)
    setSpecialty(p.specialty || '')
    setStudy(p.study || '')
    setDraft((p.rules || []).map(hydrateRule))
  }

  useEffect(() => {
    reload().catch((e) => setError(String(e.message || e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const profileMeta = useMemo(
    () => profiles.find((p) => p.slot_profile === activeProfile),
    [profiles, activeProfile],
  )

  function updateRule(idx, patch) {
    setDraft((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  }

  function removeRule(idx) {
    setDraft((prev) => prev.filter((_, i) => i !== idx))
  }

  function addRule() {
    setDraft((prev) => [...prev, emptyRule(activeProfile, specialty, study)])
  }

  function addSuggestedLabel(label) {
    if (!draft.length) {
      const r = emptyRule(activeProfile, specialty, study)
      r.pathology_labels = [label]
      r._labelsText = label
      setDraft([r])
      return
    }
    const idx = draft.length - 1
    const cur = textToLabels(draft[idx]._labelsText)
    if (cur.includes(label)) return
    const next = [...cur, label]
    updateRule(idx, { _labelsText: next.join(', '), pathology_labels: next })
  }

  async function onSave() {
    if (!activeProfile) return
    setBusy(true)
    setError('')
    setToast('')
    try {
      const rules = draft.map((r) => {
        const rads = parseRads(r._radsText)
        if (r._radsText.trim() && !rads) {
          throw new Error(`Правило ${r.id}: RADS в формате BI_RADS>=3 или BI_RADS|O_RADS>=3`)
        }
        return {
          id: r.id,
          specialty: specialty || r.specialty,
          study: study || r.study,
          target_days: Number(r.target_days) || 7,
          pathology_labels: textToLabels(r._labelsText),
          token_any: textToLabels(r._tokensText),
          rads,
          patient_message: r.patient_message || '',
        }
      })
      const res = await saveProfileTriggers(activeProfile, { specialty, study, rules })
      setProfiles(res.profiles || [])
      setVersion(res.version || version)
      const cur = (res.profiles || []).find((x) => x.slot_profile === activeProfile)
      if (cur) selectProfile(cur, res.profiles)
      setToast(`Сохранено · профиль ${activeProfile} · v${res.version}`)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="matrix-editor">
      <div className="page-head">
        <p className="eyebrow">Админ · матрица маршрутизации</p>
        <h1>Триггеры по профилям</h1>
        <p className="lede">
          Какие находки создают маршрут к специалисту. Версия матрицы: <code>{version || '—'}</code>
        </p>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {toast ? <p className="toast-inline">{toast}</p> : null}

      <div className="patient-grid">
        <section className="panel">
          <h2>Профили</h2>
          <ul className="protocol-pick">
            {profiles.map((p) => (
              <li key={p.slot_profile}>
                <button
                  type="button"
                  className={`protocol-pick-btn ${activeProfile === p.slot_profile ? 'is-active' : ''}`}
                  onClick={() => selectProfile(p)}
                >
                  <span className="protocol-pick-title">{p.slot_profile}</span>
                  <span className="muted">{p.specialty || '—'}</span>
                  <span className="sev-dot sev-suspicious">{(p.rules || []).length} правил</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>{activeProfile || 'Выберите профиль'}</h2>
          {!activeProfile ? (
            <p className="empty">Слева выберите slot_profile</p>
          ) : (
            <>
              <div className="matrix-meta">
                <label className="field">
                  <span>Специальность</span>
                  <input value={specialty} onChange={(e) => setSpecialty(e.target.value)} />
                </label>
                <label className="field">
                  <span>Исследование (по умолчанию)</span>
                  <input value={study} onChange={(e) => setStudy(e.target.value)} />
                </label>
              </div>

              <div className="chip-row" style={{ marginBottom: '0.75rem' }}>
                <button type="button" className="btn ghost" disabled={busy} onClick={addRule}>
                  + правило
                </button>
                <button type="button" className="btn primary" disabled={busy} onClick={onSave}>
                  Сохранить профиль
                </button>
              </div>

              {draft.map((r, idx) => (
                <div key={r.id} className="matrix-rule-card">
                  <div className="matrix-rule-head">
                    <label className="field" style={{ flex: 1 }}>
                      <span>id</span>
                      <input value={r.id} onChange={(e) => updateRule(idx, { id: e.target.value })} />
                    </label>
                    <label className="field" style={{ width: 100 }}>
                      <span>срок, дн</span>
                      <input
                        type="number"
                        value={r.target_days}
                        onChange={(e) => updateRule(idx, { target_days: e.target.value })}
                      />
                    </label>
                    <button type="button" className="btn ghost tiny" onClick={() => removeRule(idx)}>
                      Удалить
                    </button>
                  </div>
                  <label className="field">
                    <span>pathology_labels (через запятую)</span>
                    <textarea
                      rows={2}
                      value={r._labelsText}
                      onChange={(e) => updateRule(idx, { _labelsText: e.target.value })}
                      placeholder="полип_эндометрия, гиперплазия_эндометрия"
                    />
                  </label>
                  <label className="field">
                    <span>token_any (опционально)</span>
                    <input
                      value={r._tokensText}
                      onChange={(e) => updateRule(idx, { _tokensText: e.target.value })}
                      placeholder="МиоматозныйУзел_субмукозный"
                    />
                  </label>
                  <label className="field">
                    <span>RADS (опционально), формат PREFIX&gt;=N</span>
                    <input
                      value={r._radsText}
                      onChange={(e) => updateRule(idx, { _radsText: e.target.value })}
                      placeholder="BI_RADS>=3 или TI_RADS|EU_TIRADS>=3"
                    />
                  </label>
                  <label className="field">
                    <span>Текст пациенту</span>
                    <textarea
                      rows={3}
                      value={r.patient_message || ''}
                      onChange={(e) => updateRule(idx, { patient_message: e.target.value })}
                    />
                  </label>
                </div>
              ))}

              {suggestions.length > 0 ? (
                <details className="matrix-suggestions">
                  <summary>Подсказки pathology labels ({suggestions.length})</summary>
                  <div className="chip-row">
                    {suggestions.slice(0, 60).map((lab) => (
                      <button
                        key={lab}
                        type="button"
                        className="chip"
                        onClick={() => addSuggestedLabel(lab)}
                        title="Добавить в последнее правило"
                      >
                        {lab}
                      </button>
                    ))}
                  </div>
                </details>
              ) : null}

              {profileMeta ? (
                <p className="muted" style={{ marginTop: '0.75rem' }}>
                  Сейчас в файле: {(profileMeta.rules || []).length} правил для {activeProfile}
                </p>
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
