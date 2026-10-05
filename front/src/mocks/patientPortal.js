/** Mock patient portal: records, exam protocols, RADS alerts. */

export const PATIENT_PORTAL = {
  'pat-ivanova': {
    displayName: 'Анна Петровна',
    fullName: 'Иванова Анна Петровна',
    cardNumber: 'МК-10482',
    birthDate: '12.03.1988',
    clinic: 'СМ-Клиника',
    records: [
      {
        id: 'rec-1',
        date: '2026-09-28',
        type: 'Приём',
        title: 'Гинеколог — плановый осмотр',
        status: 'завершён',
        note: 'Направлена на УЗИ ОМТ',
      },
      {
        id: 'rec-2',
        date: '2026-09-15',
        type: 'Анализы',
        title: 'ОАК, биохимия',
        status: 'готово',
        note: 'Без критических отклонений',
      },
      {
        id: 'rec-3',
        date: '2026-08-02',
        type: 'Приём',
        title: 'Терапевт',
        status: 'завершён',
        note: 'Диспансерное наблюдение',
      },
    ],
    protocols: [
      {
        id: 'proto-omt-17',
        date: '2026-09-28',
        study: 'УЗИ органов малого таза',
        file: '1 Ж ОМТ (17).txt',
        summary: 'Гиперплазия эндометрия, полип эндометрия, миома матки',
        severity: 'suspicious',
        alertId: 'alert-rads3',
      },
      {
        id: 'proto-br-3',
        date: '2026-07-11',
        study: 'УЗИ молочных желез',
        file: 'МЖ (3).txt',
        summary: 'BI-RADS 2 слева и справа — доброкачественная картина',
        severity: 'normal',
        alertId: null,
      },
    ],
    notifications: [
      {
        id: 'alert-rads3',
        level: 'month',
        label: 'Экстренный алерт',
        radsScore: 3,
        study: 'УЗИ органов малого таза',
        createdAt: '2026-09-28T16:20:00',
        read: false,
        text:
          'Уважаемая Анна Петровна, по результатам УЗИ органов малого таза Вам рекомендовано обратиться к гинекологу в течение месяца.',
      },
      {
        id: 'notif-lab',
        level: 'info',
        label: 'Результаты анализов',
        createdAt: '2026-09-15T11:05:00',
        read: true,
        text: 'Готовы результаты ОАК и биохимии от 15.09.2026.',
      },
    ],
  },
  'pat-sidorova': {
    displayName: 'Мария Константиновна',
    fullName: 'Сидорова Мария Константиновна',
    cardNumber: 'МК-22017',
    birthDate: '04.11.1975',
    clinic: 'СМ-Клиника',
    records: [
      {
        id: 'rec-s1',
        date: '2026-10-02',
        type: 'Приём',
        title: 'Маммолог — повторный приём',
        status: 'запланирован',
        note: 'После УЗИ МЖ с BI-RADS 4',
      },
      {
        id: 'rec-s2',
        date: '2026-09-30',
        type: 'Исследование',
        title: 'УЗИ молочных желез',
        status: 'готово',
        note: 'Требует срочной консультации',
      },
    ],
    protocols: [
      {
        id: 'proto-br-8',
        date: '2026-09-30',
        study: 'УЗИ молочных желез',
        file: 'МЖ (8).txt',
        summary: 'BI-RADS 4 справа — подозрительное образование',
        severity: 'pathology',
        alertId: 'alert-rads4',
      },
      {
        id: 'proto-thy-2',
        date: '2026-05-18',
        study: 'УЗИ щитовидной железы',
        file: 'ЩЖ (2).txt',
        summary: 'EU-TIRADS 2 — без срочных действий',
        severity: 'normal',
        alertId: null,
      },
    ],
    notifications: [
      {
        id: 'alert-rads4',
        level: 'urgent',
        label: 'Срочный алерт',
        radsScore: 4,
        study: 'УЗИ молочных желез',
        createdAt: '2026-09-30T14:48:00',
        read: false,
        text:
          'Уважаемая Мария Константиновна, по результатам УЗИ молочных желез Вам необходимо срочно обратиться к маммологу.',
      },
      {
        id: 'notif-appt',
        level: 'info',
        label: 'Запись на приём',
        createdAt: '2026-10-01T09:10:00',
        read: false,
        text: 'Вам назначен приём маммолога на 02.10.2026 в 11:30.',
      },
    ],
  },
}

export function getPatientPortal(patientId) {
  return PATIENT_PORTAL[patientId] || null
}
