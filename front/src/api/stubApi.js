import { emptyRouteDraft, MOCK_ROUTES } from '../mocks/routes'

const delay = (ms = 600) => new Promise((r) => setTimeout(r, ms))

/** All API calls are stubs until FastAPI is ready */

export async function uploadDocument(_file) {
  await delay()
  return { ok: true, fileId: `file-${Date.now()}`, message: 'STUB: файл принят локально' }
}

export async function routePatient({ text, fileName }) {
  await delay(900)
  const base = emptyRouteDraft()
  // naive stub heuristic
  const lower = (text || '').toLowerCase()
  let priority = 'routine'
  let department = 'Терапия'
  let specialists = ['Терапевт']
  let reasoning = ['STUB: Decider LLM не подключён', 'Ответ сгенерирован эвристикой на фронте']

  if (lower.includes('инфаркт') || lower.includes('тропон') || lower.includes('грудин')) {
    priority = 'emergency'
    department = 'Кардиология / ОРИТ'
    specialists = ['Кардиолог', 'Реаниматолог']
    reasoning.push('Ключевые слова: кардиологические маркеры')
  } else if (lower.includes('пневмон') || lower.includes('лихорад') || lower.includes('кашел')) {
    priority = 'urgent'
    department = 'Пульмонология'
    specialists = ['Пульмонолог', 'Терапевт']
    reasoning.push('Ключевые слова: респираторные симптомы')
  }

  return {
    ...base,
    patientName: 'Пациент (из stub-пайплайна)',
    priority,
    department,
    specialists,
    requiredTests: ['ОАК', 'Биохимия'],
    reasoning,
    status: 'pending_review',
    sourceFile: fileName || 'text_input',
  }
}

export async function listRoutes() {
  await delay(300)
  return [...MOCK_ROUTES]
}

export async function saveRoute(route) {
  await delay(400)
  return { ...route, status: 'edited', savedAt: new Date().toISOString() }
}
