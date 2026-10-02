const BASE = '/api/v1'

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
    decision_json: route.decisionJson || { force_decide: true },
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

export async function listRoutes({ patientId, approved } = {}) {
  const params = new URLSearchParams()
  if (patientId) params.set('patient_id', patientId)
  if (approved === true) params.set('approved', 'true')
  if (approved === false) params.set('approved', 'false')
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

/** Бэк сам считает vector match + Decider LLM */
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
  stageLog('llm_start', `${filename || 'text'} → POST /structure (OpenRouter)`, onStage)
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

/** Split + LLM deviation filter for plain text (без полного structure) */
export async function tokenizeText(text, { timeoutMs = 120000, onStage, normalize = true } = {}) {
  stageLog('tokenize_start', 'POST /routing/tokenize', onStage)
  const res = await fetchWithRetry(
    `${BASE}/routing/tokenize`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, normalize }),
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
  stageLog(
    'tokenize_done',
    `src=${tf.source || '?'} · tokens=${(row.text_tokens || []).length} · feats=${(row.active_features || []).length} · dropped=${(tf.dropped || []).length}`,
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
