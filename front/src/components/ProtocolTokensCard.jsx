/** Protocol detail: patient, recommendation, organs, pathology highlight, full text. */

import { useMemo, useState } from 'react'
import { buildByOrganFallback, patientDisplayLabel, protocolCardNumber } from '../lib/organGroups'

const PATIENT_LABELS = {
  age_years: 'возраст (лет)',
  height_cm: 'рост (см)',
  weight_kg: 'вес (кг)',
  sex: 'пол',
}

function isNonZero(value) {
  if (value == null) return false
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0 && !Number.isNaN(value)
  if (typeof value === 'string') {
    const t = value.trim()
    if (!t) return false
    if (t === '0' || t.toLowerCase() === 'false' || t.toLowerCase() === 'null') return false
    return true
  }
  return Boolean(value)
}

/** @returns {{ key: string, label: string, value?: string, kind: 'patient'|'clinical' }[]} */
export function collectNonZeroTokens(protocol) {
  if (!protocol) return []
  const out = []
  const seen = new Set()
  const push = (key, label, value, kind) => {
    if (value == null || value === '') return
    if (!isNonZero(value) && value !== 0) return
    if (seen.has(key)) return
    seen.add(key)
    out.push({
      key,
      label: `${label}: ${value}`,
      value: String(value),
      kind,
    })
  }

  const dj = protocol.decisionJson || {}
  const patient = dj.patient || {}
  const tokens = dj.tokens || protocol.tokenMeta?.tokens || {}
  const clinical = dj.clinical_tokens || protocol.tokenMeta?.clinical_tokens || null

  for (const key of Object.keys(PATIENT_LABELS)) {
    const val = patient[key] ?? tokens[key]
    push(key, PATIENT_LABELS[key], val, 'patient')
  }

  const clinicalSrc =
    clinical ||
    Object.fromEntries(Object.entries(tokens).filter(([k]) => !PATIENT_LABELS[k]))
  for (const [k, v] of Object.entries(clinicalSrc)) {
    push(k, k, v, 'clinical')
  }

  if (!out.length) {
    for (const doc of protocol.documents || []) {
      const imp = doc.important || {}
      push('age_years', PATIENT_LABELS.age_years, imp.age, 'patient')
      push('sex', PATIENT_LABELS.sex, imp.sex, 'patient')
      const vitals = imp.vitals || {}
      push('height_cm', PATIENT_LABELS.height_cm, vitals.height_cm, 'patient')
      push('weight_kg', PATIENT_LABELS.weight_kg, vitals.weight_kg, 'patient')
    }
  }

  return out
}

function chipClass(sev) {
  if (sev === 'pathology') return 'chip is-pathology'
  if (sev === 'suspicious') return 'chip is-suspicious'
  return 'chip'
}

function TokenChips({ entries, byToken }) {
  const items = Object.entries(entries || {})
  if (!items.length) return <p className="empty muted">—</p>
  return (
    <div className="chip-row">
      {items.map(([k, v]) => (
        <span key={k} className={chipClass(byToken?.[k])} title={`${k}=${v}`}>
          {k}: {String(v)}
        </span>
      ))}
    </div>
  )
}

export default function ProtocolTokensCard({ protocol }) {
  const [showText, setShowText] = useState(false)

  const tokens = useMemo(() => collectNonZeroTokens(protocol), [protocol])
  const patientTok = tokens.filter((t) => t.kind === 'patient')

  if (!protocol) return null

  const dj = protocol.decisionJson || {}
  const tf = dj.token_filter || {}
  const junk = dj.junk || tf.dropped?.map((d) => d.token || d).filter(Boolean) || []
  const docs = protocol.documents || []
  const title =
    protocol.sourceFile ||
    docs.map((d) => d.filename).filter(Boolean).join(', ') ||
    protocol.id

  const clinicalAll = dj.clinical_tokens || protocol.tokenMeta?.clinical_tokens || dj.tokens || {}
  const recTokens = Object.keys(clinicalAll).filter((k) => k.startsWith('рекомендация_') && clinicalAll[k])
  const recommendation = dj.recommendation || protocol.tokenMeta?.recommendation || {
    present: recTokens.length > 0,
    text: null,
    specialists: [],
  }
  const specialists =
    recommendation.specialists?.length
      ? recommendation.specialists
      : recTokens.map((k) => k.replace(/^рекомендация_/, '').replace(/_/g, ' '))
  const pathology = dj.pathology || protocol.tokenMeta?.pathology || { matched: [], by_token: {} }
  const byToken = pathology.by_token || {}
  const matched = [...(pathology.matched || [])].sort((a, b) => {
    const rank = { pathology: 2, suspicious: 1 }
    return (rank[b.severity] || 0) - (rank[a.severity] || 0)
  })

  let byOrgan = dj.by_organ || protocol.tokenMeta?.by_organ || []
  if (!byOrgan.length) {
    const clinical = dj.clinical_tokens || protocol.tokenMeta?.clinical_tokens || {}
    byOrgan = buildByOrganFallback(clinical, recommendation)
  }

  return (
    <article className="protocol-card">
      <header className="protocol-card-head">
        <div>
          <h3>{title}</h3>
          <p className="muted">
            {protocolCardNumber(protocol)
              ? `Карта № ${protocolCardNumber(protocol)}`
              : patientDisplayLabel(protocol)}
            {protocol.createdAt ? ` · ${protocol.createdAt}` : ''}
            {tf.source ? ` · ${tf.source}` : ''}
            {tf.catalog_hits != null ? ` · catalog=${tf.catalog_hits}` : ''}
          </p>
        </div>
        <div className="protocol-head-badges">
          <span className={`pill ${recommendation.present || specialists.length ? 'pill-rec-yes' : 'pill-rec-no'}`}>
            {specialists.length
              ? `Направление: ${specialists.join(', ')}`
              : recommendation.present
                ? 'Рекомендация: есть'
                : 'Рекомендация: нет'}
          </span>
          <span className="pill">{tokens.length} ненулевых</span>
        </div>
      </header>

      <section className="protocol-tokens">
        <h4 className="doc-section-title">Пациент</h4>
        {patientTok.length === 0 ? (
          <p className="empty">Нет данных (возраст / рост / вес / пол)</p>
        ) : (
          <div className="chip-row">
            {patientTok.map((t) => (
              <span key={t.key} className="chip" title={t.value}>
                {t.label}
              </span>
            ))}
          </div>
        )}
        {recommendation.present && recommendation.text ? (
          <p className="rec-quote">{recommendation.text}</p>
        ) : null}
      </section>

      {(() => {
        const alert =
          dj.patient_alert || protocol.tokenMeta?.patient_alert || null
        if (!alert?.present || !alert?.text) return null
        const urgent = alert.level === 'urgent'
        return (
          <section className={`protocol-tokens patient-alert-block ${urgent ? 'is-urgent' : 'is-month'}`}>
            <h4 className="doc-section-title">
              {urgent ? 'Срочный алерт' : 'Экстренный алерт'}
              {alert.rads_score != null ? ` · RADS ${alert.rads_score}` : ''}
            </h4>
            <p className="patient-alert-text">{alert.text}</p>
          </section>
        )
      })()}

      {matched.length > 0 && (
        <section className="protocol-tokens pathology-block">
          <h4 className="doc-section-title">Патологии / подозрительное</h4>
          <ul className="pathology-list">
            {matched.map((m) => (
              <li key={m.id} className={`pathology-item sev-${m.severity}`}>
                <span className="pathology-sev">{m.severity === 'pathology' ? 'патология' : 'подозрение'}</span>
                <span>{m.label || m.id}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="protocol-tokens">
        <h4 className="doc-section-title">Описание органа или структуры</h4>
        {byOrgan.length === 0 ? (
          <p className="empty">Нет сгруппированных находок</p>
        ) : (
          <div className="organ-accordion">
            {byOrgan.map((org, idx) => {
              const key = `${org.modality}:${org.organ}`
              const susCount = Object.keys(org.suspicious || {}).length
              return (
                <details key={key} className="organ-section" open={idx < 3}>
                  <summary>
                    <strong>{org.label || org.organ}</strong>
                    <span className="muted">
                      {Object.keys(org.characteristics || {}).length} характ. · {susCount} находок
                    </span>
                  </summary>
                  <div className="organ-body">
                    <h5>Характеристики</h5>
                    <TokenChips entries={org.characteristics} byToken={byToken} />
                    <h5>Направление</h5>
                    <p className={specialists.length || recommendation.present ? 'rec-yes' : 'rec-no'}>
                      {specialists.length
                        ? `к специалисту: ${specialists.join(', ')}`
                        : recommendation.present
                          ? 'есть рекомендация'
                          : 'нет направления к специалисту'}
                    </p>
                    <h5>Подозрительные токены</h5>
                    <TokenChips entries={org.suspicious} byToken={byToken} />
                  </div>
                </details>
              )
            })}
          </div>
        )}
      </section>

      {junk.length > 0 && (
        <details className="protocol-raw">
          <summary>Junk ({junk.length})</summary>
          <div className="chip-row" style={{ marginTop: '0.5rem' }}>
            {junk.slice(0, 60).map((j, i) => (
              <span key={`${i}-${String(j).slice(0, 24)}`} className="chip chip-warn">
                {String(j).slice(0, 120)}
              </span>
            ))}
          </div>
        </details>
      )}

      <section className="protocol-text-panel">
        <button type="button" className="btn ghost" onClick={() => setShowText((v) => !v)}>
          {showText ? 'Скрыть текст протокола' : 'Полный текст протокола'}
        </button>
        {showText &&
          docs.map((d) =>
            d.rawText ? (
              <pre key={d.id || d.filename} className="raw-text">
                {d.filename ? `— ${d.filename} —\n` : ''}
                {d.rawText}
              </pre>
            ) : null,
          )}
        {showText && !docs.some((d) => d.rawText) && (
          <p className="empty">Текст документа недоступен</p>
        )}
      </section>
    </article>
  )
}
