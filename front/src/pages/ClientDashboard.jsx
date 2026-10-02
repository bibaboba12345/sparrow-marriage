import { useRef, useState } from 'react'
import { routePatient, uploadDocument } from '../api/stubApi'
import RouteCard from '../components/RouteCard'

export default function ClientDashboard() {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [text, setText] = useState('')
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [result, setResult] = useState(null)

  function onFiles(files) {
    const next = files?.[0]
    if (!next) return
    setFile(next)
    setStatus(`Выбран файл: ${next.name} (stub upload)`)
  }

  async function handleRoute() {
    if (!text.trim() && !file) {
      setStatus('Добавьте текст или файл')
      return
    }
    setLoading(true)
    setStatus('Пайплайн: upload → extract → RAG → Decider LLM… (всё stub)')
    try {
      if (file) await uploadDocument(file)
      const route = await routePatient({ text, fileName: file?.name })
      setResult(route)
      setStatus('Готово (mock JSON)')
    } catch (err) {
      setStatus(String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Client-дашборд</h1>
        <p className="lede">Загрузка выписки и получение маршрута. API — заглушки.</p>
      </header>

      <div className="split">
        <section className="panel">
          <h2>Input Zone</h2>
          <div
            className={`dropzone ${dragging ? 'active' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              onFiles(e.dataTransfer.files)
            }}
            onClick={() => inputRef.current?.click()}
          >
            <p>Перетащите PDF / DOCX сюда или нажмите для выбора</p>
            <p className="muted">{file ? file.name : 'Файл на сервер не уходит'}</p>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.docx,.txt,image/*"
              hidden
              onChange={(e) => onFiles(e.target.files)}
            />
          </div>

          <label className="field">
            <span>Текст эпикриза / анализов</span>
            <textarea
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Напр.: боль за грудиной, тропонин 1.8…"
            />
          </label>

          <div className="actions">
            <button type="button" className="btn primary" disabled={loading} onClick={handleRoute}>
              {loading ? 'Маршрутизация…' : 'Отправить в пайплайн'}
            </button>
            {status && <span className="hint">{status}</span>}
          </div>
        </section>

        <section className="panel">
          <h2>Output Zone</h2>
          {result ? (
            <RouteCard route={result} />
          ) : (
            <p className="empty">Здесь появится карточка маршрутизации с приоритетом и reasoning.</p>
          )}
        </section>
      </div>
    </div>
  )
}
