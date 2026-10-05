const BASE = '/api/v1'

/** Max upload size (must match back MAX_UPLOAD_MB, default 100) */
export const MAX_UPLOAD_MB = 100
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  if (res.status === 204) return null
  return res.json()
}

function fromDocument(doc) {
  if (!doc) return null
  return {
    id: doc.id,
    filename: doc.filename,
    filetype: doc.filetype,
    rawText: doc.raw_text || '',
    important: doc.important || {},
    metadataJunk: doc.metadata_junk || {},
    summary: doc.summary || '',
    structureModel: doc.structure_model || null,
    warnings: doc.warnings || [],
  }
}

function toDocumentPayload(doc) {
  return {
    id: doc.id,
    filename: doc.filename,
    filetype: doc.filetype || 'text',
    raw_text: doc.rawText || '',
    important: doc.important || {},
    metadata_junk: doc.metadataJunk || {},
    summary: doc.summary || '',
    structure_model: doc.structureModel || null,
    warnings: doc.warnings || [],
  }
}

/** Backend snake_case → UI camelCase */
export function fromApi(row) {
  if (!row) return null
  const documents = (row.documents || []).map(fromDocument).filter(Boolean)
  return {
    id: row.id,
    patientId: row.patient_id,
    patientName: row.patient_name,
    age: row.age,
    documents,
    rawInput: row.raw_input,
    sourceFile: row.source_file,
    priority: row.priority,
    department: row.department,
    specialists: row.specialists || [],
    requiredTests: row.required_tests || [],
    reasoning: row.reasoning || [],
    decisionJson: row.decision_json || {},
    status: row.status,
    approved: Boolean(row.approved),
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  }
}

export function toCreatePayload(route) {
  return {
    patient_id: route.patientId,
    patient_name: route.patientName,
    age: route.age ?? null,
    documents: (route.documents || []).map(toDocumentPayload),
    raw_input: route.rawInput || '',
    source_file: route.sourceFile || null,
    priority: route.priority || 'routine',
    department: route.department || '',
    specialists: route.specialists || [],
    required_tests: route.requiredTests || [],
    reasoning: route.reasoning || [],
    decision_json: route.decisionJson || {},
    status: route.status || 'pending_review',
    approved: false,
  }
}

export function toUpdatePayload(route) {
  return {
    patient_name: route.patientName,
    age: route.age ?? null,
    documents: route.documents ? route.documents.map(toDocumentPayload) : undefined,
    priority: route.priority,
    department: route.department,
    specialists: route.specialists || [],
    required_tests: route.requiredTests || [],
    reasoning: route.reasoning || [],
    decision_json: route.decisionJson || {},
    status: route.status || 'edited',
    approved: false,
  }
}

export function decideFromText() {
  // deprecated: routing считается на бэке (vector match + Decider)
  return {
    priority: 'routine',
    department: '',
    specialists: [],
    requiredTests: [],
    reasoning: [],
    decisionJson: { force_decide: true },
  }
}

export async function listRoutes({ patientId, approved, priority } = {}) {
  const params = new URLSearchParams()
  if (patientId) params.set('patient_id', patientId)
  if (approved === true) params.set('approved', 'true')
  if (approved === false) params.set('approved', 'false')
  if (priority) params.set('priority', priority)
  const qs = params.toString()
  const rows = await request(`/routes${qs ? `?${qs}` : ''}`)
  return rows.map(fromApi)
}

export async function listPatients() {
  const rows = await request('/patients')
  return rows.map((p) => ({
    patientId: p.patient_id,
    patientName: p.patient_name,
  }))
}

export async function getRoute(id) {
  return fromApi(await request(`/routes/${encodeURIComponent(id)}`))
}

export async function createRoute(route) {
  const row = await request('/routes', {
    method: 'POST',
    body: JSON.stringify(toCreatePayload(route)),
  })
  return fromApi(row)
}

export async function updateRoute(route) {
  const row = await request(`/routes/${encodeURIComponent(route.id)}`, {
    method: 'PATCH',
    body: JSON.stringify(toUpdatePayload(route)),
  })
  return fromApi(row)
}

export async function approveRoute(id) {
  return fromApi(
    await request(`/routes/${encodeURIComponent(id)}/approve`, { method: 'POST' }),
  )
}

export async function deleteRoute(id) {
  await request(`/routes/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/** Бэк сам считает vector match + Decider LLM (только при force_decide) */
export async function routePatient({ documents, patientId, patientName, age, onStage }) {
  if (!patientId) {
    throw new Error('patientId обязателен — берётся из сессии клиента')
  }
  if (!documents?.length) {
    throw new Error('Добавьте хотя бы один документ')
  }
  onStage?.({ stage: 'decide_start', detail: 'POST /routes → vectorize+match+decider', t: Date.now() })
  console.log('[sparrow:decide_start]', documents.length, 'docs')
  const route = await createRoute({
    patientId,
    patientName: patientName || 'Пациент',
    age: age ?? null,
    documents,
    department: '',
    reasoning: [],
    decisionJson: { force_decide: true },
    status: 'pending_review',
    approved: false,
  })
  const dj = route.decisionJson || {}
  onStage?.({
    stage: 'decide_done',
    detail: `case=${dj.matched_case_id || '?'} score=${dj.match_score ?? '?'} src=${dj.decider_source || '?'}`,
    t: Date.now(),
  })
  console.log('[sparrow:decide_done]', dj)
  return route
}

function slugPatientId(name, sex, age) {
  const raw = `${name || ''}|${sex || ''}|${age ?? ''}`.toLowerCase()
  let h = 0
  for (let i = 0; i < raw.length; i += 1) h = (h * 31 + raw.charCodeAt(i)) >>> 0
  return `pat-${h.toString(16)}`
}

/** Normalize card number for id/display. */
export function normalizeCardNumber(raw) {
  return String(raw || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
}

/** patient_id from card number (stable, filesystem-safe). */
export function cardNumberToPatientId(card) {
  const n = normalizeCardNumber(card)
  if (!n) return null
  const slug = n
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
  return slug ? `card-${slug}` : null
}

/** Try «Номер карты: …» / «Амбулаторная карта № …» from protocol text. */
export function extractCardNumberFromText(blob) {
  const t = String(blob || '').replace(/\u00a0/g, ' ')
  const patterns = [
    /Номер\s*карты\s*[:\t]\s*([^\n\r]{1,80})/i,
    /Амбулаторн\w*\s*карт\w*\s*№\s*([^\n\r]{1,80})/i,
    /Карт\w*\s*№\s*([^\n\r]{1,80})/i,
  ]
  for (const re of patterns) {
    const m = t.match(re)
    if (!m) continue
    let val = normalizeCardNumber(m[1])
    // cut trailing tabs / labels glued on same line
    val = val.split(/\t/)[0].replace(/\s{2,}.*/, '').trim()
    if (val && val.length >= 1) return val.slice(0, 80)
  }
  return null
}

function guessPatientNameFromText(blob, important, patient) {
  const fromImp = (important?.patient_name || '').trim()
  if (fromImp) return fromImp
  const m = String(blob || '').match(/(?:ФИО\s*пациента|Пациент)\s*[:\t]\s*([^\n\r,]{3,80})/i)
  if (m) {
    const name = m[1].trim()
    if (name && !/^[\.\-—]+$/.test(name)) return name.slice(0, 80)
  }
  const sex = patient?.sex
  const age = patient?.age_years
  const bits = ['Пациент']
  if (sex) bits.push(sex)
  if (age != null) bits.push(`${age} лет`)
  if (bits.length > 1) return bits.join(' · ')
  return 'Без имени'
}

/**
 * Сохранить протокол: patient + catalog tokens + by_organ + pathology.
 */
export async function saveProtocol({
  documents,
  patientId = null,
  patientName = null,
  cardNumber = null,
  age = null,
  tokenMeta = null,
  onStage,
} = {}) {
  if (!documents?.length) {
    throw new Error('Добавьте хотя бы один документ')
  }
  let merged = { ...(tokenMeta || {}) }
  for (const doc of documents) {
    const tm = doc.tokenMeta || {}
    if (!merged.tokens && tm.tokens) merged.tokens = tm.tokens
    if (!merged.patient && tm.patient) merged.patient = tm.patient
    if (!merged.clinical_tokens && tm.clinical_tokens) {
      merged.clinical_tokens = tm.clinical_tokens
    }
    if (!merged.junk?.length && tm.junk?.length) merged.junk = tm.junk
    if (!merged.text_tokens?.length && tm.text_tokens?.length) {
      merged.text_tokens = tm.text_tokens
    }
    if (!merged.token_filter && tm.token_filter) merged.token_filter = tm.token_filter
    if (!merged.important && tm.important) merged.important = tm.important
    if (!merged.recommendation && tm.recommendation) merged.recommendation = tm.recommendation
    if (!merged.by_organ && tm.by_organ) merged.by_organ = tm.by_organ
    if (!merged.pathology && tm.pathology) merged.pathology = tm.pathology
    if (!merged.organs_present && tm.organs_present) merged.organs_present = tm.organs_present
    if (!merged.patient_alert && tm.patient_alert) merged.patient_alert = tm.patient_alert
  }

  const blob = documents
    .map((d) => d.rawText || '')
    .filter(Boolean)
    .join('\n\n')
  const needTok =
    !merged.tokens ||
    !Object.values(merged.tokens).some((v) => v != null && v !== '')
  if (needTok && blob.trim()) {
    try {
      const tok = await tokenizeText(blob, { onStage })
      merged = {
        patient: tok.patient || {},
        tokens: tok.tokens || {},
        clinical_tokens: tok.clinical_tokens || {},
        junk: tok.junk || [],
        text_tokens: tok.text_tokens || [],
        token_filter: tok.token_filter || {},
        important: tok.important || {},
        active_features: tok.active_features || [],
        recommendation: tok.recommendation || {},
        by_organ: tok.by_organ || [],
        organs_present: tok.organs_present || [],
        pathology: tok.pathology || {},
        patient_alert: tok.patient_alert || null,
      }
      documents = documents.map((d) => ({
        ...d,
        important: tok.important || d.important || {},
        tokenMeta: {
          patient: tok.patient,
          tokens: tok.tokens,
          clinical_tokens: tok.clinical_tokens,
          junk: tok.junk,
          text_tokens: tok.text_tokens,
          token_filter: tok.token_filter,
          recommendation: tok.recommendation,
          by_organ: tok.by_organ,
          organs_present: tok.organs_present,
          pathology: tok.pathology,
          patient_alert: tok.patient_alert,
        },
      }))
    } catch (err) {
      console.warn('[sparrow:saveProtocol] tokenize failed', err)
      merged.token_filter = { source: 'error', error: String(err?.message || err) }
      merged.tokens = merged.tokens || {}
      merged.junk = merged.junk || []
    }
  }

  const ageFromTokens = merged.patient?.age_years ?? merged.tokens?.age_years
  const card =
    normalizeCardNumber(cardNumber) ||
    extractCardNumberFromText(blob) ||
    ''
  const cardId = cardNumberToPatientId(card)
  const resolvedId = patientId || cardId || null
  if (!resolvedId) {
    throw new Error('Укажите номер карты перед сохранением')
  }
  const resolvedName =
    patientName ||
    (card ? `Карта № ${card}` : null) ||
    guessPatientNameFromText(blob, merged.important, merged.patient)
  onStage?.({ stage: 'save_start', detail: 'POST /routes (patient + catalog tokens)', t: Date.now() })
  const sourceFile = documents.map((d) => d.filename).filter(Boolean).join(', ') || null
  const alert = merged.patient_alert || null
  const alertPriority =
    alert?.level === 'urgent' ? 'emergency' : alert?.level === 'month' ? 'urgent' : 'routine'
  const route = await createRoute({
    patientId: resolvedId,
    patientName: resolvedName,
    age: age ?? ageFromTokens ?? null,
    documents,
    rawInput: blob,
    sourceFile,
    department: '',
    reasoning: alert?.text ? [alert.text] : [],
    specialists: alert?.specialist ? [alert.specialist] : [],
    requiredTests: [],
    priority: alertPriority,
    decisionJson: {
      patient: {
        ...(merged.patient || {}),
        ...(card ? { card_number: card } : {}),
      },
      tokens: merged.tokens || {},
      clinical_tokens: merged.clinical_tokens || {},
      junk: merged.junk || [],
      text_tokens: merged.text_tokens || [],
      active_features: merged.active_features || [],
      matched_phrases: [],
      token_filter: merged.token_filter || {},
      recommendation: merged.recommendation || { present: false, text: null },
      by_organ: merged.by_organ || [],
      organs_present: merged.organs_present || [],
      pathology: merged.pathology || { matched: [], by_token: {} },
      patient_alert: alert,
      card_number: card || null,
      decider_source: 'skipped',
    },
    status: 'tokenized',
    approved: false,
  })
  const n = Object.values(route.decisionJson?.tokens || {}).filter((v) => v != null && v !== '').length
  onStage?.({
    stage: 'save_done',
    detail: `id=${route.id} · tokens=${n}`,
    t: Date.now(),
  })
  return route
}

export async function saveRoute(route) {
  return updateRoute({ ...route, status: 'edited', approved: false })
}

function stageLog(stage, detail, onStage) {
  const entry = { stage, detail: detail || '', t: Date.now() }
  console.log(`[sparrow:${stage}]`, detail || '')
  onStage?.(entry)
  return entry
}

async function fetchWithTimeout(url, options, timeoutMs, label) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (err) {
    if (err?.name === 'AbortError') {
      throw new Error(`Таймаут на этапе «${label}» (>${Math.round(timeoutMs / 1000)}с)`)
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

const RETRY_STATUSES = new Set([408, 429, 500, 502, 503, 504])

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** fetch with timeout + retry on Bad Gateway / transient errors */
async function fetchWithRetry(
  url,
  options,
  timeoutMs,
  label,
  { retries = 3, onStage } = {},
) {
  let lastErr
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      const res = await fetchWithTimeout(url, options, timeoutMs, label)
      if (res.ok || !RETRY_STATUSES.has(res.status) || attempt === retries) {
        return res
      }
      const body = await res.text()
      lastErr = new Error(`${label} ${res.status}: ${body}`)
      stageLog(
        'retry',
        `${label} → ${res.status}, повтор ${attempt}/${retries}`,
        onStage,
      )
      await sleep(Math.min(1500 * 2 ** (attempt - 1), 8000))
    } catch (err) {
      lastErr = err
      const msg = String(err?.message || err).toLowerCase()
      const retryable =
        msg.includes('таймаут') ||
        msg.includes('timeout') ||
        msg.includes('network') ||
        msg.includes('failed to fetch')
      if (!retryable || attempt === retries) throw err
      stageLog('retry', `${label} сеть/таймаут, повтор ${attempt}/${retries}`, onStage)
      await sleep(Math.min(1500 * 2 ** (attempt - 1), 8000))
    }
  }
  throw lastErr || new Error(`${label} failed`)
}

/** Только extract файла, без LLM */
export async function extractDocument(file, { timeoutMs = 30000, onStage } = {}) {
  if (file?.size > MAX_UPLOAD_BYTES) {
    const mb = (file.size / (1024 * 1024)).toFixed(1)
    throw new Error(`Файл слишком большой: ${mb} МБ (лимит ${MAX_UPLOAD_MB} МБ)`)
  }
  stageLog('extract_start', `${file.name} → POST /upload?structure=false`, onStage)
  const form = new FormData()
  form.append('file', file)
  const res = await fetchWithRetry(
    `${BASE}/upload?structure=false`,
    { method: 'POST', body: form },
    timeoutMs,
    'extract PDF/DOCX',
    { onStage },
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`extract ${res.status}: ${body}`)
  }
  const row = await res.json()
  stageLog(
    'extract_done',
    `${row.engine} · ${row.char_count} символов · ${row.filetype}`,
    onStage,
  )
  return {
    filename: row.filename,
    filetype: row.filetype,
    engine: row.engine,
    text: row.text,
    charCount: row.char_count,
    warnings: row.warnings || [],
  }
}

/** LLM structure уже извлечённого текста */
export async function structureDocument(text, { filename, timeoutMs = 180000, onStage } = {}) {
  stageLog('llm_start', `${filename || 'text'} → POST /structure`, onStage)
  const res = await fetchWithRetry(
    `${BASE}/structure`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, filename }),
    },
    timeoutMs,
    'LLM structure',
    { onStage },
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`structure ${res.status}: ${body}`)
  }
  const row = await res.json()
  stageLog('llm_done', `model=${row.model || '?'} · summary=${(row.summary || '').slice(0, 80)}`, onStage)
  return {
    important: row.important || {},
    metadataJunk: row.metadata_junk || {},
    summary: row.summary || '',
    structureModel: row.model || null,
  }
}

/** Strict objective tokens: age/height/weight/sex → tokens; rest → junk */
export async function tokenizeText(text, { timeoutMs = 120000, onStage, filename } = {}) {
  stageLog('tokenize_start', 'POST /routing/tokenize (objective)', onStage)
  const res = await fetchWithRetry(
    `${BASE}/routing/tokenize`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, filename }),
    },
    timeoutMs,
    'tokenize text',
    { onStage },
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`tokenize ${res.status}: ${body}`)
  }
  const row = await res.json()
  const tf = row.token_filter || {}
  const nTok = Object.values(row.tokens || {}).filter((v) => v != null && v !== '').length
  const nClin = Object.keys(row.clinical_tokens || {}).length
  stageLog(
    'tokenize_done',
    `src=${tf.source || '?'} · tokens=${nTok} · clinical=${nClin} · junk=${(row.junk || []).length}`,
    onStage,
  )
  return row
}

/**
 * Полный пайплайн одного файла с логами этапов:
 * extract → llm structure → document
 */
export async function processDocument(file, { onStage, extractTimeoutMs = 30000, llmTimeoutMs = 180000 } = {}) {
  stageLog('queued', file.name, onStage)
  const extracted = await extractDocument(file, { timeoutMs: extractTimeoutMs, onStage })

  let structured = {
    important: {},
    metadataJunk: {},
    summary: '',
    structureModel: null,
  }
  const warnings = [...(extracted.warnings || [])]

  try {
    structured = await structureDocument(extracted.text, {
      filename: extracted.filename,
      timeoutMs: llmTimeoutMs,
      onStage,
    })
  } catch (err) {
    const msg = err.message || String(err)
    warnings.push(`LLM structure failed: ${msg}`)
    stageLog('llm_error', msg, onStage)
  }

  stageLog('document_ready', extracted.filename, onStage)
  const document = {
    id: `doc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    filename: extracted.filename,
    filetype: extracted.filetype,
    rawText: extracted.text,
    important: structured.important,
    metadataJunk: structured.metadataJunk,
    summary: structured.summary,
    structureModel: structured.structureModel,
    warnings,
  }

  return {
    ok: true,
    ...extracted,
    structured: {
      important: structured.important,
      metadata_junk: structured.metadataJunk,
      summary: structured.summary,
    },
    structureModel: structured.structureModel,
    warnings,
    document,
  }
}

/** @deprecated use processDocument — оставлен для совместимости */
export async function uploadDocument(file, opts = {}) {
  return processDocument(file, opts)
}
