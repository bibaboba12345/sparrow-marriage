import { useEffect, useRef, useState } from 'react'
import { processDocument, routePatient, tokenizeText } from '../api/routesApi'
import { useAuth } from '../auth/AuthContext'
import DocumentsPanel from '../components/DocumentsPanel'
import RouteCard from '../components/RouteCard'

const STAGE_LABEL = {
  queued: 'В очереди',
  extract_start: '1/4 Extract — отправка файла',
  extract_done: '1/4 Extract — готово',
  llm_start: '2/4 LLM structure — ждём OpenRouter',
  llm_done: '2/4 LLM structure — готово',
  llm_error: '2/4 LLM structure — ошибка (текст всё равно сохранён)',
  retry: 'Повтор после Bad Gateway / ошибки',
  tokenize_start: 'Токенизация текста — LLM filter',
  tokenize_done: 'Токенизация — готово',
  document_ready: '3/4 Документ собран',
  decide_start: '4/4 Decider — vector match + LLM',
  decide_done: '4/4 Decider — готово',
}

export default function ClientDashboard() {
  const { user } = useAuth()
  const inputRef = useRef(null)
  const [documents, setDocuments] = useState([])
  const [draftText, setDraftText] = useState(
    'Жалобы: боль за грудиной с иррадиацией в левую руку, одышка, тошнота. Температура 36.6. Сердцебиение в норме.',
  )
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [status, setStatus] = useState('')
  const [stage, setStage] = useState(null)
  const [stageLog, setStageLog] = useState([])
  const [elapsedSec, setElapsedSec] = useState(0)
  const [result, setResult] = useState(null)
  const startedAtRef = useRef(null)

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
    console.log('[sparrow] batch start', files.map((f) => f.name))
    const added = []
    try {
      for (let i = 0; i < files.length; i += 1) {
        const file = files[i]
        console.log(`[sparrow] file ${i + 1}/${files.length}`, file.name)
        const extracted = await processDocument(file, { onStage: pushStage })
        added.push(extracted.document)
      }
      setDocuments((prev) => [...prev, ...added])
      setStatus(`Готово · добавлено ${added.length} · в тикете будет ${documents.length + added.length}`)
      setStage('document_ready')
    } catch (err) {
      console.error('[sparrow] batch error', err)
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
      setStatus('Введите текст жалоб / эпикриза')
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
      important = {
        ...(tok.important || {}),
        clinical_snippets: tok.text_tokens || [],
      }
      tokenMeta = {
        text_tokens: tok.text_tokens || [],
        active_features: tok.active_features || [],
        matched_phrases: tok.matched_phrases || [],
        token_filter: tok.token_filter || {},
      }
      const dropped = (tok.token_filter || {}).dropped || []
      if (dropped.length) {
        warnings.push(`dropped ${dropped.length}: ${dropped.map((d) => d.token).filter(Boolean).join('; ')}`)
      }
    } catch (err) {
      console.error('[sparrow] tokenize error', err)
      warnings.push(`tokenize failed: ${err.message || err}`)
      // fallback: локальный split по запятым, чтобы документ всё равно был с токенами
      important = {
        symptoms: text
          .split(/[,;\n]+/)
          .map((s) => s.trim())
          .filter((s) => s.length > 1),
        red_flags: [],
        clinical_snippets: [],
      }
      pushStage({ stage: 'llm_error', detail: err.message || String(err), t: Date.now() })
    }

    const doc = {
      id: `doc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      filename: 'epicrisis.txt',
      filetype: 'text',
      rawText: text,
      important,
      metadataJunk: {},
      summary: '',
      structureModel: tokenMeta?.token_filter?.model || null,
      warnings,
      tokenMeta,
    }
    setDocuments((prev) => [...prev, doc])
    const nSym = (important.symptoms || []).length
    const nFeat = (tokenMeta?.active_features || []).length
    setStatus(`Текст токенизирован · ${nSym} жалоб · ${nFeat} features · в тикете`)
    setStage('document_ready')
    setExtracting(false)
  }

  async function handleRoute() {
    if (!documents.length) {
      setStatus('Добавьте хотя бы один документ')
      return
    }
    setLoading(true)
    setStage('ticket_save')
    setStatus('3/3 Создание routing-тикета → POST /routes')
    console.log('[sparrow] ticket_save', documents.length, 'docs')
    try {
      setStage('decide_start')
      setStatus('Decider: vectorize → match → LLM…')
      const route = await routePatient({
        documents,
        patientId: user.id,
        patientName: user.name,
        onStage: pushStage,
      })
      setResult(route)
      setStatus(`Тикет ${route.id} · ${route.documents.length} док. · patient=${user.id}`)
      console.log('[sparrow] ticket_done', route.id)
      setDocuments([])
      setStageLog([])
      setStage(null)
    } catch (err) {
      console.error('[sparrow] ticket error', err)
      setStatus(`Ошибка API: ${err.message || err}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Client-дашборд</h1>
        <p className="lede">
          {user.name} · <code>{user.id}</code> — несколько документов в одном routing-тикете, токены по файлам.
        </p>
      </header>

      <div className="split">
        <section className="panel">
          <h2>Input Zone</h2>
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
            <p>Перетащите PDF / DOCX / TXT (можно несколько) или нажмите</p>
            <p className="muted">
              {extracting
                ? `${STAGE_LABEL[stage] || stage || 'Обработка'} · ${elapsedSec}с`
                : 'Каждый файл → extract → LLM → document'}
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
            <span>Или вставьте текст жалоб / эпикриза</span>
            <textarea
              rows={5}
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              placeholder="Жалобы: …"
              disabled={extracting || loading}
            />
            <button
              type="button"
              className="btn ghost"
              disabled={extracting || loading || !draftText.trim()}
              onClick={addTextDoc}
            >
              Добавить текст в тикет
            </button>
          </label>

          {(extracting || stageLog.length > 0) && (
            <div className="stage-box">
              <div className="stage-head">
                <strong>Этапы запроса</strong>
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
              <p className="hint">Подробности также в DevTools → Console (`[sparrow:…]`)</p>
            </div>
          )}

          {documents.length > 0 && (
            <div className="pending-docs">
              <div className="pending-head">
                <h3>Документы в тикете ({documents.length})</h3>
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
                        · {(doc.important?.symptoms || []).length} symptoms ·{' '}
                        {(doc.important?.red_flags || []).length} flags ·{' '}
                        {(doc.important?.labs || []).length} labs
                        {doc.tokenMeta?.active_features?.length
                          ? ` · ${doc.tokenMeta.active_features.length} feats`
                          : ''}
                      </span>
                    </div>
                    <button type="button" className="btn danger" onClick={() => removeDoc(doc.id)}>
                      Убрать
                    </button>
                  </li>
                ))}
              </ul>
              <DocumentsPanel documents={documents} />
            </div>
          )}

          <div className="actions">
            <button
              type="button"
              className="btn primary"
              disabled={loading || extracting || !documents.length}
              onClick={handleRoute}
            >
              {loading ? 'Сохранение…' : 'Отправить тикет'}
            </button>
            {status && <span className="hint">{status}</span>}
          </div>
        </section>

        <section className="panel">
          <h2>Output Zone</h2>
          {result ? (
            <RouteCard route={result} />
          ) : (
            <p className="empty">После сабмита здесь будет тикет с документами и маршрутом.</p>
          )}
        </section>
      </div>
    </div>
  )
}
