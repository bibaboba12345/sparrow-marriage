# Front (Sparrow Route)

Простой React-фронт с кучей заглушек под хакатон.

## Запуск

```bash
cd front
npm install
npm run dev
```

Откроется http://localhost:5173

## Stub-логины

| Логин  | Пароль | Роль   |
|--------|--------|--------|
| client | client | client |
| admin  | admin  | admin  |
| doctor | 1234   | client |

## Что есть

- `/login` — login + password (localStorage, без бэкенда)
- `/client` — Input Zone (drag-and-drop + текст) → mock маршрутизация
- `/admin` — список mock-карточек + редактирование (Human-in-the-loop)

API лежит в `src/api/stubApi.js` — потом заменить на FastAPI (`/api` уже проксируется на `:8000`).
