# Backend (Sparrow Route)

FastAPI + SQLite. Route-записи + PDF/DOCX extractors.

## Запуск

```bash
cd back
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger: http://localhost:8000/docs
- БД: `app/data/routes.db`

## Extractors + LLM structure

| Модуль | Файл |
|--------|------|
| PDF | `app/extractors/pdf_extractor.py` |
| Word | `app/extractors/word_extractor.py` |
| Schema | `app/extractors/structure_schema.py` — `important` + `metadata_junk` |
| LLM | `app/extractors/llm_structurer.py` — DeepSeek via OpenAI SDK |

Ключ в `back/.env` (см. `.env.example`):

```bash
cp .env.example .env
# DEEPSEEK_API_KEY=sk-...
```

`POST /api/v1/upload?structure=true` → `{ text, structured: { important, metadata_junk, summary }, ... }`  
`POST /api/v1/structure` body `{"text":"..."}` — только LLM-разбор.

## Эндпоинты

| Метод | Путь | Что делает |
|-------|------|------------|
| `POST` | `/api/v1/upload` | Extract PDF/DOCX/TXT |
| `POST` | `/api/v1/routing/tokenize` | Токены + pathology + patient_alert |
| `GET` | `/api/v1/routes` | Список (+ `patient_id`, `approved`) |
| `POST` | `/api/v1/routes` | Создать (+ авто-создание ClinicalJourney) |
| `POST` | `/api/v1/journeys/from-protocol` | Создать маршрут из clinical/pathology |
| `GET` | `/api/v1/journeys` | Список маршрутов |
| `POST` | `/api/v1/journeys/{id}/book` | Запись на stub-слот |
| `POST` | `/api/v1/journeys/{id}/tactics` | Тактика врача |
| `GET` | `/api/v1/schedule/slots` | Заглушка слотов |
| `GET` | `/api/v1/notifications` | Уведомления пациента |
| `GET` | `/api/v1/coordinator/tasks` | Задачи координатора |
| `GET` | `/api/v1/analytics/funnel` | Воронка конверсии |
| `POST` | `/api/v1/demo/clock` | Модельное время |
| `POST` | `/api/v1/demo/seed-journeys` | Seed сценариев |
| `POST` | `/api/v1/mis/events` | Вебхук-заглушка МИС |

Матрица: `app/routing/routing_matrix.json` · движок: `app/routing/journey_engine.py` · контракты: `../docs/integrations.md`

