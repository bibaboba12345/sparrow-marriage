# Интеграции (заглушки)

Прототип не подключается к реальной 1С / SMS / push. Ниже — контракты, которые команда показывает на защите.

## Расписание (Schedule stub)

`GET /api/v1/schedule/slots?profile={slot_profile}&journey_id=`

Ответ:

```json
{
  "slots": [
    {
      "id": "slot-operating_gyn-0-…",
      "profile": "operating_gyn",
      "modality": "online",
      "location": "Онлайн",
      "doctor": "Иванова Е.А.",
      "specialty": "оперирующий гинеколог",
      "starts_at": "2026-10-05T14:00:00Z"
    }
  ]
}
```

Профили: `operating_gyn`, `mammologist`, `surgeon_abd`, `endocrinologist`, `urologist`.

Запись: `POST /api/v1/journeys/{id}/book` с телом `{ "slot": {…}, "kind": "consult"|"control" }`.

## Уведомления

Каналы: `cabinet` (личный кабинет, приоритет), `push`, `sms`, `call_task` (задача координатору).

Создаются движком при создании маршрута и эскалациях. Журнал: таблица `notifications` + `journey_events`.

`GET /api/v1/notifications?patient_id=`

## События МИС

`POST /api/v1/mis/events`

```json
{
  "event_id": "unique-idempotency-key",
  "kind": "protocol_voided|protocol_amended|appointment_completed|appointment_no_show|hospitalized|service_rendered|discharged",
  "journey_id": "jn-…",
  "appointment_id": "ap-…",
  "service": "surgery",
  "clinical": {},
  "pathology": {}
}
```

Повтор с тем же `event_id` не создаёт дублей (`processed_mis_events`).

## Модельное время

`GET/POST /api/v1/demo/clock` — `{ "hours": 24 }` / `{ "days": 7 }` / `{ "reset": true }`.

При сдвиге вызывается `process_due_escalations` (24ч / 72ч / ~6д звонок / 14д / 30д).

## Матрица маршрутизации

Файл настроек: `back/app/routing/routing_matrix.json` (не хардкод).  
`GET /api/v1/routing/matrix`
