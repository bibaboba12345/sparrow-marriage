/** Client fallback: coarse organ grouping when decisionJson.by_organ is missing. */

const PREFIXES = [
  ['ЖелчныйПузырь_', 'Желчный пузырь'],
  ['КонкрементЖП_', 'Желчный пузырь'],
  ['ПолипЖП_', 'Желчный пузырь'],
  ['Холедох_', 'Желчный пузырь'],
  ['Печень_', 'Печень'],
  ['ВоротнаяВена_', 'Печень'],
  ['ПеченочныеВены_', 'Печень'],
  ['ВнутрипеченочныеПротоки_', 'Печень'],
  ['Поджелудочная_', 'Поджелудочная железа'],
  ['ВирсунговПроток_', 'Поджелудочная железа'],
  ['Селезенка_', 'Селезенка'],
  ['Матка_', 'Матка'],
  ['Миометрий_', 'Матка'],
  ['МиоматозныйУзел_', 'Матка'],
  ['Эндометрий_', 'Матка'],
  ['ПолостьМатки_', 'Матка'],
  ['ШейкаМатки_', 'Матка'],
  ['ЦервикальныйКанал_', 'Матка'],
  ['КистаШейки_', 'Матка'],
  ['ПолипШейки_', 'Матка'],
  ['ПолипЭндометрия_', 'Матка'],
  ['ЯичникПравый_', 'Яичники'],
  ['ЯичникЛевый_', 'Яичники'],
  ['КистаЯичника_', 'Яичники'],
  ['O_RADS_', 'Яичники'],
  ['ТрубаПравая_', 'Маточные трубы'],
  ['ТрубаЛевая_', 'Маточные трубы'],
  ['МЖ_', 'Молочная железа'],
  ['BI_RADS_', 'Молочная железа'],
  ['МлечныеПротоки_', 'Молочная железа'],
  ['киста_МЖ_', 'Молочная железа'],
  ['КистаМЖ_', 'Молочная железа'],
  ['ОчагМЖ_', 'Молочная железа'],
  ['Фиброаденома_', 'Молочная железа'],
  ['КальцинатМЖ_', 'Молочная железа'],
  ['Имплант_', 'Молочная железа'],
  ['лимфузлы_аксиллярные_', 'Лимфоузлы'],
  ['ЛимфоузелАксиллярный_', 'Лимфоузлы'],
  ['Щитовидная_', 'Щитовидная железа'],
  ['ДоляПравая_', 'Щитовидная железа'],
  ['ДоляЛевая_', 'Щитовидная железа'],
  ['Перешеек_', 'Щитовидная железа'],
  ['УзелЩЖ_', 'Щитовидная железа'],
  ['КистаЩЖ_', 'Щитовидная железа'],
  ['TI_RADS', 'Щитовидная железа'],
  ['лимфузлы_шейные_', 'Лимфоузлы'],
  ['Простата_', 'Предстательная железа'],
  ['ПереходнаяЗона_', 'Предстательная железа'],
  ['АденоматозныйУзел_', 'Предстательная железа'],
  ['КистаПростаты_', 'Предстательная железа'],
  ['ОстаточнаяМоча_', 'Мочевой пузырь'],
  ['МочевойПузырь_', 'Мочевой пузырь'],
  ['ОбщаяБедреннаяАртерия_', 'Артерии НК'],
  ['ПоверхностнаяБедреннаяАртерия_', 'Артерии НК'],
  ['БПВ_', 'Вены НК'],
  ['МПВ_', 'Вены НК'],
]

const EXPLICIT = {
  миома_матки: 'Матка',
  аденомиоз: 'Матка',
  эндометриоз: 'Матка',
  гиперплазия_эндометрия: 'Матка',
  полип_эндометрия: 'Матка',
  стеатоз_печени: 'Печень',
  диффузные_изменения_печени: 'Печень',
  конкременты_желчного_пузыря: 'Желчный пузырь',
  полип_желчного_пузыря: 'Желчный пузырь',
  дискинезия_желчного_пузыря: 'Желчный пузырь',
  киста_яичника_R: 'Яичники',
  киста_яичника_L: 'Яичники',
  свободная_жидкость_за_маткой: 'Матка',
  узел_щитовидной: 'Щитовидная железа',
  узел_щитовидной_R: 'Щитовидная железа',
  узел_щитовидной_L: 'Щитовидная железа',
  киста_щитовидной: 'Щитовидная железа',
  АИТ_признаки: 'Щитовидная железа',
  объем_щитовидной_см3: 'Щитовидная железа',
  гиперплазия_простаты: 'Предстательная железа',
  киста_простаты: 'Предстательная железа',
  мастопатия: 'Молочная железа',
  киста_молочной_железы: 'Молочная железа',
  фиброаденома: 'Молочная железа',
  фиброаденома_R: 'Молочная железа',
  фиброаденома_L: 'Молочная железа',
  мастопексия: 'Молочная железа',
  импланты_МЖ: 'Молочная железа',
  варикозное_расширение_вен: 'Вены НК',
}

function isNonZero(value) {
  if (value == null) return false
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0 && !Number.isNaN(value)
  if (typeof value === 'string') {
    const t = value.trim()
    if (!t || t === '0' || t.toLowerCase() === 'false') return false
    return true
  }
  return Boolean(value)
}

function organLabel(name) {
  if (name.startsWith('рекомендация_')) return null
  if (Object.prototype.hasOwnProperty.call(EXPLICIT, name)) return EXPLICIT[name]
  for (const [pref, label] of PREFIXES) {
    if (name.startsWith(pref) || name === pref.replace(/_$/, '')) return label
  }
  return 'Прочее'
}

function looksBinary(value) {
  return value === 1 || value === true
}

export function buildByOrganFallback(clinical, recommendation) {
  const bags = new Map()
  for (const [name, val] of Object.entries(clinical || {})) {
    if (name.startsWith('рекомендация_') || name.startsWith('study_')) continue
    if (!isNonZero(val)) continue
    const label = organLabel(name)
    if (!label) continue
    if (!bags.has(label)) {
      bags.set(label, { label, organ: label, modality: 'unknown', characteristics: {}, suspicious: {} })
    }
    const slot = bags.get(label)
    if (looksBinary(val)) slot.suspicious[name] = 1
    else slot.characteristics[name] = val
  }
  const present = Boolean(recommendation?.present)
  return [...bags.values()].map((x) => ({
    ...x,
    recommendation: { present },
  }))
}

/** Card number from protocol record (decisionJson / patientName / patientId). */
export function protocolCardNumber(protocol) {
  const dj = protocol?.decisionJson || {}
  const fromDj = (dj.card_number || dj.patient?.card_number || '').toString().trim()
  if (fromDj) return fromDj
  const name = (protocol?.patientName || '').trim()
  const m = name.match(/^Карта\s*№\s*(.+)$/i)
  if (m) return m[1].trim()
  const pid = (protocol?.patientId || '').trim()
  if (pid.startsWith('card-')) {
    return pid.slice(5).replace(/-/g, ' ')
  }
  return ''
}

/** Filter key = card / patient_id (not FIO). */
export function patientFilterKey(protocol) {
  const card = protocolCardNumber(protocol)
  if (card) return `card:${card.toLowerCase()}`
  return `id:${protocol?.patientId || protocol?.id || ''}`
}

export function patientDisplayLabel(protocol) {
  const card = protocolCardNumber(protocol)
  const dj = protocol?.decisionJson || {}
  const p = dj.patient || {}
  const parts = []
  if (card) parts.push(`Карта № ${card}`)
  if (p.sex) parts.push(p.sex === 'ж' ? 'жен' : p.sex === 'м' ? 'муж' : p.sex)
  const age = p.age_years ?? protocol?.age
  if (age != null && age !== '') parts.push(`${age} лет`)
  if (parts.length) return parts.join(' · ')
  const name = (protocol?.patientName || '').trim()
  if (name && name.toLowerCase() !== 'admin') return name
  return 'Без номера карты'
}
