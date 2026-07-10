import { useEffect, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

function App() {
  const [backendStatus, setBackendStatus] = useState<'checking' | 'ok' | 'error'>('checking')

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`status ${res.status}`))))
      .then(() => setBackendStatus('ok'))
      .catch(() => setBackendStatus('error'))
  }, [])

  return (
    <main>
      <h1>기업지원 종합 사이트</h1>
      <p>
        Backend: <strong>{backendStatus}</strong>
      </p>
    </main>
  )
}

export default App
