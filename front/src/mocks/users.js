/** Stub credentials — no real auth. У каждого client ровно один стабильный id. */
export const STUB_USERS = [
  {
    login: 'client',
    password: 'client',
    role: 'client',
    id: 'pat-ivanova',
    name: 'Иванова А.П.',
  },
  {
    login: 'admin',
    password: 'admin',
    role: 'admin',
    id: 'admin-petrov',
    name: 'Петров В.С.',
  },
  {
    login: 'doctor',
    password: '1234',
    role: 'client',
    id: 'pat-sidorova',
    name: 'Сидорова М.К.',
  },
]
