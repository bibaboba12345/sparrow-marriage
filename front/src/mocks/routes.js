/** Mock routing decisions — replace with FastAPI later */

export const PRIORITY = {
  emergency: { key: 'emergency', label: 'Экстренное', tone: 'emergency' },
  urgent: { key: 'urgent', label: 'Срочное', tone: 'urgent' },
  routine: { key: 'routine', label: 'Плановое', tone: 'routine' },
}

export const MOCK_ROUTES = [
  {
    id: 'pt-001',
    patientName: 'Козлов И.Н.',
    age: 54,
    createdAt: '2026-10-01T09:14:00',
    priority: 'emergency',
    department: 'Кардиология / ОРИТ',
    specialists: ['Кардиолог', 'Реаниматолог'],
    requiredTests: ['Тропонин I', 'ЭКГ', 'Д-димер'],
    reasoning: [
      'Боль за грудиной > 30 мин, иррадиация в левую руку',
      'Тропонин повышен (цитата из выписки: «TnI 1.8 нг/мл»)',
      'Протокол ACS / STEMI — экстренная маршрутизация',
    ],
    status: 'pending_review',
    sourceFile: 'epicrisis_kozlov.pdf',
  },
  {
    id: 'pt-002',
    patientName: 'Морозова Е.В.',
    age: 31,
    createdAt: '2026-10-01T11:02:00',
    priority: 'urgent',
    department: 'Терапия',
    specialists: ['Терапевт', 'Пульмонолог'],
    requiredTests: ['ОАК', 'СРБ', 'Рентген ОГК'],
    reasoning: [
      'Лихорадка 38.7°C 4 дня, кашель с мокротой',
      'СРБ 48 мг/л',
      'Гайдлайн: внебольничная пневмония — срочный приём',
    ],
    status: 'approved',
    sourceFile: 'labs_morozova.pdf',
  },
  {
    id: 'pt-003',
    patientName: 'Смирнов Д.А.',
    age: 67,
    createdAt: '2026-09-30T16:40:00',
    priority: 'routine',
    department: 'Эндокринология',
    specialists: ['Эндокринолог'],
    requiredTests: ['HbA1c', 'Глюкоза натощак'],
    reasoning: [
      'HbA1c 7.2%, стабильная компенсация',
      'Нет острых осложнений',
      'Плановый контроль по протоколу СД 2 типа',
    ],
    status: 'edited',
    sourceFile: 'manual_input',
  },
]

export function emptyRouteDraft() {
  return {
    id: `pt-draft-${Date.now()}`,
    patientName: 'Новый пациент (stub)',
    age: null,
    createdAt: new Date().toISOString(),
    priority: 'routine',
    department: '—',
    specialists: [],
    requiredTests: [],
    reasoning: ['Ожидание ответа Decider LLM (stub)'],
    status: 'draft',
    sourceFile: null,
  }
}
