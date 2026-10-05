# Sparrow Route — хирургическая воронка (прототип)

Единая цифровая воронка: **протокол УЗИ → профильный врач → решение → госпитализация → операция → контроль**.

## Быстрый старт

```bash
# backend
cd back
source .venv/bin/activate   # или python -m venv .venv && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend
cd front
npm install
npm run dev
```

Открыть http://localhost:5173 · API docs http://localhost:8000/docs

Seed маршрутов:

```bash
curl -X POST http://localhost:8000/api/v1/demo/seed-journeys
```

## Учётки (stub)

| Логин | Пароль | Экран |
|-------|--------|--------|
| `client` | `client` | Кабинет пациента (Иванова) |
| `doctor` | `doctor` | МИС-форма врача |
| `coord` | `coord` | Координатор |
| `admin` | `admin` | Протоколы + воронка + все экраны |

## Демо-сценарии

1. **Happy path:** пациент `client` → Seed → Записаться → слот → врач `doctor` → завершить с тактикой «Оперативное лечение» → coord назначает дату госпитализации → `POST /mis/events` hospitalized/operated/discharged.
2. **Не записался:** Seed → в кабинете +24ч / +72ч / +7д / +14д / +30д — уведомления и задачи координатору.
3. **Неявка:** запись → врач «Неявка» → эскалации как в сценарии 2.

Модельное время: кнопки в кабинете пациента / на дашборде воронки, либо `POST /api/v1/demo/clock`.

## Архитектура

- Извлечение фактов: `protocol_tokenizer` + `pathology_rules.json`
- Решение о маршруте: `routing_matrix.json` + `journey_engine.py` (детерминированно)
- Заглушки: расписание, SMS/push, события 1С — см. [docs/integrations.md](docs/integrations.md)

## Безопасность (прототип)

Система не ставит диагноз и не назначает лечение; пациенту — нейтральные тексты; экстренное — эскалация персоналу.
