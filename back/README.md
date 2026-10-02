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
| `GET` | `/api/v1/routes` | Список (+ `patient_id`, `approved`) |
| `POST` | `/api/v1/routes` | Создать |
| `POST` | `/api/v1/routes/{id}/approve` | APPROVE |
| `DELETE` | `/api/v1/routes/{id}` | Удалить |
| `PATCH` | `/api/v1/routes/{id}` | HITL-правка |
| `GET` | `/api/v1/patients` | Юзеры для фильтра |
| `POST` | `/api/v1/seed` | Демо, если пусто |
