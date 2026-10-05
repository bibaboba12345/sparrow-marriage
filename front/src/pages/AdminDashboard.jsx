import { useCallback, useEffect, useRef, useState } from 'react'
import {
  MAX_UPLOAD_MB,
  deleteRoute,
  extractCardNumberFromText,
  extractDocument,
  listRoutes,
  normalizeCardNumber,
  saveProtocol,
  tokenizeText,
} from '../api/routesApi'
import ProtocolTokensCard, { collectNonZeroTokens } from '../components/ProtocolTokensCard'
import MatrixEditor from '../components/MatrixEditor'
import { patientDisplayLabel, patientFilterKey, protocolCardNumber } from '../lib/organGroups'

function packTokenMeta(tok) {
  return {
    patient: tok.patient || {},
    tokens: tok.tokens || {},
    clinical_tokens: tok.clinical_tokens || {},
    junk: tok.junk || [],
    text_tokens: tok.text_tokens || [],
    token_filter: tok.token_filter || {},
    important: tok.important || {},
    recommendation: tok.recommendation || {},
    by_organ: tok.by_organ || [],
    organs_present: tok.organs_present || [],
    pathology: tok.pathology || {},
    patient_alert: tok.patient_alert || null,
  }
}

const STAGE_LABEL = {
  queued: 'В очереди',
  extract_start: 'Extract — отправка файла',
  extract_done: 'Extract — готово',
  llm_error: 'Токенизация — ошибка',
  retry: 'Повтор после ошибки',
  tokenize_start: 'Токены — patient + catalog',
  tokenize_done: 'Токены — готово',
  document_ready: 'Документ собран',
  save_start: 'Сохранение протокола',
  save_done: 'Протокол сохранён',
}

const TABS = [
  { id: 'protocols', label: 'Очередь' },
  { id: 'upload', label: 'Загрузка' },
  { id: 'matrix', label: 'Матрица' },
]

const QUEUE_TIERS = [
  {
    id: 'pathology',
    title: 'Патология',
    hint: 'есть патологические находки — проверить в первую очередь',
  },
  {
    id: 'suspicious',
    title: 'Подозрение',
    hint: 'подозрительные признаки без явной патологии',
  },
  {
    id: 'normal',
    title: 'Норма',
    hint: 'без патологии и подозрений',
  },
]

function protocolQueueTier(p) {
  const matched = p?.decisionJson?.pathology?.matched || []
  const byToken = p?.decisionJson?.pathology?.by_token || {}
  const sevs = new Set([
    ...matched.map((m) => m.severity).filter(Boolean),
    ...Object.values(byToken).filter(Boolean),
  ])
  if (sevs.has('pathology')) return 'pathology'
  if (sevs.has('suspicious')) return 'suspicious'
  return 'normal'
}

export default function AdminDashboard() {
  const inputRef = useRef(null)
  const [tab, setTab] = useState('protocols')
  const [protocols, setProtocols] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [patientFilter, setPatientFilter] = useState('')
  const [cardNumber, setCardNumber] = useState('')

  const [documents, setDocuments] = useState([])
  const [draftText, setDraftText] = useState('')
  const [dragging, setDragging] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [status, setStatus] = useState('')
  const [stage, setStage] = useState(null)
  const [stageLog, setStageLog] = useState([])
  const [elapsedSec, setElapsedSec] = useState(0)
  const startedAtRef = useRef(null)

  const patientOptions = Array.from(
    new Map(
      protocols.map((p) => {
        const card = protocolCardNumber(p)
        const label = card ? `Карта № ${card}` : patientDisplayLabel(p)
        return [patientFilterKey(p), label]
      }),
    ).entries(),
  ).sort((a, b) => a[1].localeCompare(b[1], 'ru'))

  function maybeFillCardFromText(text) {
    const found = extractCardNumberFromText(text)
    if (!found) return
    setCardNumber((prev) => (normalizeCardNumber(prev) ? prev : found))
  }

  const filteredProtocols = patientFilter
    ? protocols.filter((p) => patientFilterKey(p) === patientFilter)
    : protocols

  const queueByTier = QUEUE_TIERS.map((tier) => ({
    ...tier,
    items: filteredProtocols.filter((p) => protocolQueueTier(p) === tier.id),
  }))

  const selected = filteredProtocols.find((p) => p.id === selectedId)
    || protocols.find((p) => p.id === selectedId)
    || null

  function renderProtocolRow(p) {
    const n = collectNonZeroTokens(p).length
    const title =
      p.sourceFile ||
      (p.documents || []).map((d) => d.filename).filter(Boolean).join(', ') ||
      p.id
    const recSpecs = p.decisionJson?.recommendation?.specialists || []
    const recToks = Object.keys(p.decisionJson?.clinical_tokens || {}).filter((k) =>
      k.startsWith('рекомендация_'),
    )
    const rec =
      p.decisionJson?.recommendation?.present ||
      recSpecs.length > 0 ||
      recToks.length > 0
    const pathN = (p.decisionJson?.pathology?.matched || []).filter(
      (m) => m.severity === 'pathology',
    ).length
    const susN = (p.decisionJson?.pathology?.matched || []).filter(
      (m) => m.severity === 'suspicious',
    ).length
    const tier = protocolQueueTier(p)
    return (
      <li key={p.id}>
        <button
          type="button"
          className={`route-list-item tier-${tier} ${selectedId === p.id ? 'active' : ''}`}
          onClick={() => {
            setSelectedId(p.id)
            setToast('')
          }}
        >
          <div className="route-list-top">
            <strong>{title}</strong>
            <span className="pill">{n}</span>
          </div>
          <span className="muted">{patientDisplayLabel(p)}</span>
          <span className="route-list-meta muted">
            {p.createdAt || p.id}
            {recSpecs.length
              ? ` · → ${recSpecs.join(', ')}`
              : recToks.length
                ? ` · → ${recToks.map((k) => k.replace(/^рекомендация_/, '')).join(', ')}`
                : rec
                  ? ' · рек.'
                  : ''}
            {pathN ? ` · пат.${pathN}` : ''}
            {susN ? ` · под.${susN}` : ''}
          </span>
        </button>
      </li>
    )
  }

  const load = useCallback(async (preferId) => {
    setLoading(true)
    setError('')
    try {
      const data = await listRoutes({})
      setProtocols(data)
      setSelectedId((prev) => {
        const want = preferId || prev
        if (want && data.some((r) => r.id === want)) return want
        return data[0]?.id ?? null
      })
    } catch (err) {
      setError(`Не удалось загрузить протоколы: ${err.message || err}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!extracting) return undefined
    startedAtRef.current = Date.now()
    setElapsedSec(0)
    const id = setInterval(() => {
      setElapsedSec(Math.round((Date.now() - startedAtRef.current) / 1000))
    }, 500)
    return () => clearInterval(id)
  }, [extracting])

  function pushStage(entry) {
    setStage(entry.stage)
    setStageLog((prev) => [...prev.slice(-20), entry])
    const label = STAGE_LABEL[entry.stage] || entry.stage
    setStatus(`${label}${entry.detail ? ` · ${entry.detail}` : ''}`)
  }

  async function onFiles(fileList) {
    const files = Array.from(fileList || [])
    if (!files.length) return
    setExtracting(true)
    setStageLog([])
    setStage('queued')
    setStatus(`Обработка ${files.length} файл(ов)…`)
    const added = []
    try {
      for (const file of files) {
        const extracted = await extractDocument(file, { onStage: pushStage })
        const tok = await tokenizeText(extracted.text, {
          onStage: pushStage,
          filename: extracted.filename,
        })
        added.push({
          id: `doc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
          filename: extracted.filename,
          filetype: extracted.filetype,
          rawText: extracted.text,
          important: tok.important || {},
          metadataJunk: { other_noise: tok.junk || [] },
          summary: '',
          structureModel: tok.token_filter?.model || null,
          warnings: extracted.warnings || [],
          tokenMeta: packTokenMeta(tok),
        })
      }
      setDocuments((prev) => [...prev, ...added])
      const blob = added.map((d) => d.rawText || '').join('\n')
      maybeFillCardFromText(blob)
      setStatus(`Готово · добавлено ${added.length}`)
      setStage('document_ready')
    } catch (err) {
      setStatus(`Ошибка: ${err.message || err}`)
      setStage('error')
    } finally {
      setExtracting(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function removeDoc(id) {
    setDocuments((prev) => prev.filter((d) => d.id !== id))
  }

  async function addTextDoc() {
    const text = draftText.trim()
    if (!text) {
      setStatus('Введите текст протокола')
      return
    }
    setExtracting(true)
    setStageLog([])
    setStage('tokenize_start')
    setStatus('Токенизация текста…')
    const warnings = ['manual text input']
    let important = {}
    let tokenMeta = null
    try {
      const tok = await tokenizeText(text, { onStage: pushStage })
      important = tok.important || {}
      tokenMeta = packTokenMeta(tok)
      if ((tok.junk || []).length) {
        warnings.push(`junk ${tok.junk.length}`)
      }
    } catch (err) {
      warnings.push(`tokenize failed: ${err.message || err}`)
      pushStage({ stage: 'llm_error', detail: err.message || String(err), t: Date.now() })
    }

    const doc = {
      id: `doc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      filename: 'protocol.txt',
      filetype: 'text',
      rawText: text,
      important,
      metadataJunk: { other_noise: tokenMeta?.junk || [] },
      summary: '',
      structureModel: tokenMeta?.token_filter?.model || null,
      warnings,
      tokenMeta,
    }
    setDocuments((prev) => [...prev, doc])
    maybeFillCardFromText(text)
    const n = Object.values(tokenMeta?.tokens || {}).filter((v) => v != null && v !== '').length
    setStatus(`Текст токенизирован · ${n} objective · junk ${(tokenMeta?.junk || []).length}`)
    setStage('document_ready')
    setExtracting(false)
  }

  async function handleSaveProtocol() {
    if (!documents.length) {
      setStatus('Добавьте хотя бы один документ')
      return
    }
    const card = normalizeCardNumber(cardNumber)
    if (!card) {
      setStatus('Укажите номер карты')
      setToast('Нужен номер карты')
      return
    }
    setBusy(true)
    setToast('')
    try {
      const saved = await saveProtocol({
        documents,
        cardNumber: card,
        onStage: pushStage,
      })
      setDocuments([])
      setDraftText('')
      setCardNumber('')
      setStageLog([])
      setStage(null)
      setStatus(`Сохранено · ${saved.id}`)
      const jn = saved.decisionJson?.journey
      const jMsg = jn?.triggered
        ? ` · маршрут ${(jn.journey_ids || []).join(',')}`
        : jn
          ? ' · без хир. триггера'
          : ''
      setToast(`Протокол ${saved.id} · карта № ${card}${jMsg}`)
      setTab('protocols')
      setPatientFilter(patientFilterKey(saved))
      await load(saved.id)
    } catch (err) {
      setStatus(`Ошибка сохранения: ${err.message || err}`)
      setToast(`Ошибка: ${err.message || err}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!selected) return
    if (!window.confirm(`Удалить протокол ${selected.id}?`)) return
    setBusy(true)
    setToast('')
    try {
      await deleteRoute(selected.id)
      setToast(`Удалено · ${selected.id}`)
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
        <h1>Очередь проверки</h1>
        <p className="lede">
          Патология → подозрение → норма · фильтр по номеру карты · токенизация протоколов.
        </p>
      </header>

      <nav className="tab-bar" aria-label="Разделы">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`tab-btn ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'protocols' && (
        <>
          <section className="panel filters-bar">
            <label className="filter-patient">
              <span className="muted">Номер карты</span>
              <select
                value={patientFilter}
                onChange={(e) => {
                  setPatientFilter(e.target.value)
                  setSelectedId(null)
                }}
              >
                <option value="">Все карты</option>
                {patientOptions.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn ghost" disabled={loading || busy} onClick={() => load()}>
              Обновить
            </button>
            {toast && <span className="hint">{toast}</span>}
          </section>

          {loading ? (
            <p className="muted">Загрузка…</p>
          ) : error ? (
            <p className="error">{error}</p>
          ) : (
            <div className="split admin-split">
              <section className="panel list-panel">
                <h2>
                  Очередь ({filteredProtocols.length}
                  {patientFilter ? ` / ${protocols.length}` : ''})
                </h2>
                <div className="queue-summary">
                  {queueByTier.map((tier) => (
                    <span key={tier.id} className={`queue-chip queue-${tier.id}`}>
                      {tier.title}: {tier.items.length}
                    </span>
                  ))}
                </div>
                {filteredProtocols.length === 0 ? (
                  <p className="empty">
                    {protocols.length === 0
                      ? 'Пока пусто. Загрузите протокол во вкладке «Загрузка».'
                      : 'Нет протоколов для выбранной карты.'}
                  </p>
                ) : (
                  <div className="queue-tiers">
                    {queueByTier.map((tier) => (
                      <details
                        key={tier.id}
                        className={`queue-tier queue-${tier.id}`}
                        open={tier.id !== 'normal' || tier.items.length > 0}
                      >
                        <summary>
                          <span className="queue-tier-title">{tier.title}</span>
                          <span className="pill">{tier.items.length}</span>
                          <span className="muted queue-tier-hint">{tier.hint}</span>
                        </summary>
                        {tier.items.length === 0 ? (
                          <p className="empty muted">Пусто</p>
                        ) : (
                          <ul className="route-list">{tier.items.map(renderProtocolRow)}</ul>
                        )}
                      </details>
                    ))}
                  </div>
                )}
              </section>

              <section className="panel">
                <h2>Токены</h2>
                {selected ? (
                  <>
                    <ProtocolTokensCard protocol={selected} />
                    <div className="actions admin-actions">
                      <button type="button" className="btn danger" disabled={busy} onClick={handleDelete}>
                        Удалить
                      </button>
                    </div>
                    {toast && <p className="hint">{toast}</p>}
                  </>
                ) : (
                  <p className="empty">Выберите протокол слева</p>
                )}
              </section>
            </div>
          )}
        </>
      )}

      {tab === 'upload' && (
        <div className="split">
          <section className="panel">
            <h2>Загрузка протокола</h2>
            <label className="field">
              <span>Номер карты</span>
              <input
                type="text"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                placeholder="Напр. 1 Ж ОМТ (21) — подставится из текста, если есть"
                disabled={extracting || busy}
                autoComplete="off"
              />
            </label>
            <div
              className={`dropzone ${dragging ? 'active' : ''}`}
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                onFiles(e.dataTransfer.files)
              }}
              onClick={() => inputRef.current?.click()}
            >
              <p>Перетащите PDF / DOCX / TXT или нажмите</p>
              <p className="muted">
                {extracting
                  ? `${STAGE_LABEL[stage] || stage || 'Обработка'} · ${elapsedSec}с`
                  : `Extract → objective tokens (возраст/рост/вес) · лимит ${MAX_UPLOAD_MB} МБ`}
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                multiple
                hidden
                onChange={(e) => onFiles(e.target.files)}
              />
            </div>

            <label className="field text-input-block">
              <span>Или вставьте текст протокола</span>
              <textarea
                rows={6}
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                placeholder="Текст УЗИ / эпикриза…"
                disabled={extracting || busy}
              />
              <button
                type="button"
                className="btn ghost"
                disabled={extracting || busy || !draftText.trim()}
                onClick={addTextDoc}
              >
                Добавить текст
              </button>
            </label>

            {(extracting || stageLog.length > 0) && (
              <div className="stage-box">
                <div className="stage-head">
                  <strong>Этапы</strong>
                  {extracting && <span className="pill">{elapsedSec}с</span>}
                </div>
                <ol className="stage-list">
                  {stageLog.map((entry, idx) => (
                    <li key={`${entry.t}-${idx}`} className={entry.stage === stage ? 'active' : ''}>
                      <code>{entry.stage}</code>
                      <span>{STAGE_LABEL[entry.stage] || entry.stage}</span>
                      {entry.detail ? <span className="muted"> — {entry.detail}</span> : null}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {documents.length > 0 && (
              <div className="pending-docs">
                <div className="pending-head">
                  <h3>К сохранению ({documents.length})</h3>
                  <button type="button" className="btn ghost" onClick={() => setDocuments([])}>
                    Очистить
                  </button>
                </div>
                <ul className="pending-list">
                  {documents.map((doc) => (
                    <li key={doc.id} className="pending-item">
                      <div>
                        <strong>{doc.filename}</strong>
                        <span className="muted">
                          {' '}
                          ·{' '}
                          {
                            Object.values(doc.tokenMeta?.tokens || {}).filter(
                              (v) => v != null && v !== '',
                            ).length
                          }{' '}
                          tokens
                          {doc.tokenMeta?.junk?.length
                            ? ` · junk ${doc.tokenMeta.junk.length}`
                            : ''}
                        </span>
                      </div>
                      <button type="button" className="btn danger" onClick={() => removeDoc(doc.id)}>
                        Убрать
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="actions">
              <button
                type="button"
                className="btn primary"
                disabled={busy || extracting || !documents.length}
                onClick={handleSaveProtocol}
              >
                {busy ? 'Сохранение…' : 'Сохранить протокол'}
              </button>
              {status && <span className="hint">{status}</span>}
            </div>
          </section>

          <section className="panel">
            <h2>Превью токенов</h2>
            {documents.length ? (
              <ProtocolTokensCard
                protocol={{
                  id: 'preview',
                  documents,
                  decisionJson: {
                    patient:
                      documents.find((d) => d.tokenMeta?.patient)?.tokenMeta?.patient || {},
                    tokens: documents.find((d) => d.tokenMeta?.tokens)?.tokenMeta?.tokens || {},
                    clinical_tokens:
                      documents.find((d) => d.tokenMeta?.clinical_tokens)?.tokenMeta
                        ?.clinical_tokens || {},
                    junk: documents.flatMap((d) => d.tokenMeta?.junk || []),
                    text_tokens: documents.flatMap((d) => d.tokenMeta?.text_tokens || []),
                    token_filter: documents.find((d) => d.tokenMeta?.token_filter)?.tokenMeta
                      ?.token_filter,
                    recommendation: documents.find((d) => d.tokenMeta?.recommendation)
                      ?.tokenMeta?.recommendation,
                    by_organ: documents.find((d) => d.tokenMeta?.by_organ)?.tokenMeta?.by_organ,
                    pathology: documents.find((d) => d.tokenMeta?.pathology)?.tokenMeta?.pathology,
                    patient_alert: documents.find((d) => d.tokenMeta?.patient_alert)?.tokenMeta
                      ?.patient_alert,
                    organs_present: documents.find((d) => d.tokenMeta?.organs_present)
                      ?.tokenMeta?.organs_present,
                  },
                }}
              />
            ) : (
              <p className="empty">Добавьте файл или текст — здесь появятся ненулевые токены.</p>
            )}
          </section>
        </div>
      )}

      {tab === 'matrix' && <MatrixEditor />}
    </div>
  )
}
