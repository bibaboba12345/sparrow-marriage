/** Clinical journey / funnel / demo clock API client */

async function request(path, { method = 'GET', body } = {}) {
  const opts = {
    method,
    headers: { Accept: 'application/json' },
  }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(`/api/v1${path}`, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || JSON.stringify(j)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export function createJourneysFromProtocol(payload) {
  return request('/journeys/from-protocol', { method: 'POST', body: payload })
}

export function listJourneys({ patientId, status } = {}) {
  const q = new URLSearchParams()
  if (patientId) q.set('patient_id', patientId)
  if (status) q.set('status', status)
  const s = q.toString()
  return request(`/journeys${s ? `?${s}` : ''}`)
}

export function getJourney(id) {
  return request(`/journeys/${id}`)
}

export function bookJourney(id, slot, kind = 'consult') {
  return request(`/journeys/${id}/book`, { method: 'POST', body: { slot, kind } })
}

export function appointmentOutcome(id, outcome, appointmentId = null) {
  return request(`/journeys/${id}/appointment-outcome`, {
    method: 'POST',
    body: { outcome, appointment_id: appointmentId },
  })
}

export function setTactics(id, tactics, createReferral = true) {
  return request(`/journeys/${id}/tactics`, {
    method: 'POST',
    body: { tactics, create_referral: createReferral },
  })
}

export function setHospitalizationDate(id, when = null) {
  return request(`/journeys/${id}/hospitalization-date`, {
    method: 'POST',
    body: { when },
  })
}

export function patientResponse(id, action) {
  return request(`/journeys/${id}/patient-response`, {
    method: 'POST',
    body: { action },
  })
}

export function listSlots(profile, journeyId) {
  const q = new URLSearchParams({ profile })
  if (journeyId) q.set('journey_id', journeyId)
  return request(`/schedule/slots?${q}`)
}

export function listNotifications(patientId) {
  return request(`/notifications?patient_id=${encodeURIComponent(patientId)}`)
}

export function markNotificationRead(id) {
  return request(`/notifications/${id}/read`, { method: 'POST', body: {} })
}

export function listCoordinatorTasks(state = 'open') {
  const q = state ? `?state=${encodeURIComponent(state)}` : ''
  return request(`/coordinator/tasks${q}`)
}

export function completeTask(id) {
  return request(`/coordinator/tasks/${id}/complete`, { method: 'POST', body: {} })
}

export function getClock() {
  return request('/demo/clock')
}

export function advanceClock({ hours = 0, days = 0, reset = false } = {}) {
  return request('/demo/clock', { method: 'POST', body: { hours, days, reset } })
}

export function getFunnel() {
  return request('/analytics/funnel')
}

export function seedDemoJourneys() {
  return request('/demo/seed-journeys', { method: 'POST', body: {} })
}

export function postMisEvent(payload) {
  return request('/mis/events', { method: 'POST', body: payload })
}

export const TACTICS_OPTIONS = [
  { id: 'surgery', label: 'Оперативное лечение показано' },
  { id: 'extra_exam', label: 'Требуется дополнительное обследование' },
  { id: 'watch', label: 'Динамическое наблюдение' },
  { id: 'no_surgery', label: 'Операция не показана' },
  { id: 'refused', label: 'Пациент отказался' },
  { id: 'other_profile', label: 'Направление в другой профиль' },
]

export const STAGE_LABELS = {
  detected: 'Выявлен триггер',
  notified: 'Уведомлён',
  booked: 'Записан',
  visit_done: 'Приём состоялся',
  tactics_chosen: 'Тактика выбрана',
  referral_created: 'Направление на госпитализацию',
  hospitalization_scheduled: 'Госпитализация назначена',
  hospitalized: 'Госпитализирован',
  operated: 'Оперирован',
  discharged: 'Выписан',
  control_booked: 'Контроль назначен',
  control_done: 'Контроль пройден',
  needs_rebook: 'Требуется запись',
  no_show: 'Неявка',
  not_engaged: 'Не вовлечён',
  abandoned: 'Закрыт',
}

export function getMatrixProfiles() {
  return request('/routing/matrix/profiles')
}

export function getMatrix() {
  return request('/routing/matrix')
}

export function saveProfileTriggers(profile, { specialty, study, rules }) {
  return request(`/routing/matrix/profiles/${encodeURIComponent(profile)}`, {
    method: 'PUT',
    body: { specialty, study, rules },
  })
}

export function getPathologyLabels() {
  return request('/routing/pathology-labels')
}
