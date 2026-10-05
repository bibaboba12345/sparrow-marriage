# Front (Sparrow Route)

React-фронт → FastAPI через Vite proxy `/api` → `:8000`.

## Запуск

```bash
# terminal 1
cd back && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# terminal 2
cd front && npm install && npm run dev
```

http://localhost:5173

## Stub-логины

| Логин | Пароль | Куда |
|-------|--------|------|
| client | client | /patient |
| doctor | doctor | /doctor |
| coord | coord | /coordinator |
| admin | admin | /admin (+ ссылки на все экраны) |

## Экраны воронки

- **Пациент** — маршруты, колокольчик, запись на stub-слоты, демо-часы
- **Врач** — баннер маршрута, обязательная тактика
- **Координатор** — звонки / госпитализация
- **Воронка** (`/manager`) — конверсия диагностического потока

API-клиент: `src/api/journeyApi.js`
