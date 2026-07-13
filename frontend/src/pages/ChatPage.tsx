import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from '../lib/api'
import { useAuth } from '../lib/auth'

interface ChatOption {
  label: string
  value: string
}

interface QuestionMessage {
  type: 'question'
  question_id: string
  text: string
  options: ChatOption[]
}

interface MatchReason {
  criterion: string
  status: string
  evidence: string | null
}

interface ChatMatch {
  policy_id: string
  title: string
  score: number
  reasons: MatchReason[]
}

interface ResultMessage {
  type: 'result'
  matches: ChatMatch[]
}

interface ErrorMessage {
  type: 'error'
  message: string
}

type ServerMessage = QuestionMessage | ResultMessage | ErrorMessage
type ConnectionStatus = 'connecting' | 'open' | 'closed'

const WS_BASE = API_BASE.replace(/^http/, 'ws')
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000]

function getSessionId(companyId: string): string {
  const key = `chat_session_id:${companyId}`
  let id = localStorage.getItem(key)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(key, id)
  }
  return id
}

function statusLabel(status: ConnectionStatus): string {
  if (status === 'open') return '연결됨'
  if (status === 'connecting') return '연결 중...'
  return '연결 끊김 (재시도 중)'
}

export default function ChatPage() {
  const { companyId, token } = useAuth()
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [question, setQuestion] = useState<QuestionMessage | null>(null)
  const [result, setResult] = useState<ChatMatch[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const startedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(companyId ? getSessionId(companyId) : null)

  const connect = useCallback(() => {
    if (!companyId || !token) return
    const sessionId = sessionIdRef.current
    if (!sessionId) return

    setStatus('connecting')
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${sessionId}?token=${encodeURIComponent(token)}`)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('open')
      attemptRef.current = 0
      if (!startedRef.current) {
        startedRef.current = true
        ws.send(JSON.stringify({ type: 'start', company_id: companyId }))
      }
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as ServerMessage
      if (data.type === 'question') {
        setQuestion(data)
        setResult(null)
        setError(null)
      } else if (data.type === 'result') {
        setResult(data.matches)
        setQuestion(null)
        setError(null)
      } else {
        setError(data.message)
      }
    }

    ws.onclose = () => {
      setStatus('closed')
      wsRef.current = null
      const delay = RECONNECT_DELAYS_MS[Math.min(attemptRef.current, RECONNECT_DELAYS_MS.length - 1)]
      attemptRef.current += 1
      window.setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [companyId, token])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  function answer(value: string) {
    if (!question || wsRef.current?.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({ type: 'answer', question_id: question.question_id, value }))
    setQuestion(null)
  }

  function restart() {
    if (!companyId) return
    localStorage.removeItem(`chat_session_id:${companyId}`)
    sessionIdRef.current = getSessionId(companyId)
    startedRef.current = false
    setQuestion(null)
    setResult(null)
    setError(null)
    wsRef.current?.close()
  }

  return (
    <main className="page page-narrow">
      <h1>맞춤 상담 채팅</h1>
      <p className="chat-status">연결 상태: {statusLabel(status)}</p>
      {error && <p className="error-text">{error}</p>}
      {question && (
        <div className="chat-question">
          <p>{question.text}</p>
          <div className="chat-options">
            {question.options.map((opt) => (
              <button key={opt.value} onClick={() => answer(opt.value)}>
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {result && (
        <div className="chat-result">
          <h2>매칭 결과</h2>
          <ul className="match-list">
            {result.map((match) => (
              <li key={match.policy_id} className="match-card">
                <div className="match-card-header">
                  <span className="match-title">{match.title}</span>
                  <span className={`score-badge score-${match.score >= 70 ? 'high' : match.score >= 40 ? 'mid' : 'low'}`}>
                    {match.score}점
                  </span>
                </div>
              </li>
            ))}
          </ul>
          <button onClick={restart}>새 상담 시작</button>
        </div>
      )}
      {!question && !result && status === 'open' && <p>매칭을 계산하는 중입니다...</p>}
    </main>
  )
}
