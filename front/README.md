# Front (Sparrow Route)

React-фронт, ходит в FastAPI/SQLite через Vite proxy.

## Запуск

Терминал 1 — бэк:
```bash
cd back
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
# по желанию: curl -X POST http://localhost:8000/api/v1/seed
```

Терминал 2 — фронт:
```bash
cd front
npm install
npm run dev
```

http://localhost:5173 · proxy `/api` → `:8000`

## Stub-логины

| Логин  | Пароль | Роль   |
|--------|--------|--------|
| client | client | client |
| admin  | admin  | admin  |
| doctor | 1234   | client |

## Что подключено к БД

- **Client** `POST /api/v1/routes` — raw_input + эвристика → запись в SQLite
- **Admin** `GET /api/v1/routes` — все записи
- **Admin** `PATCH /api/v1/routes/{id}` — HITL-правки

Клиент API: `src/api/routesApi.js`
