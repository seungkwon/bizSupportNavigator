import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { API_BASE } from '../lib/api'
import { useAuth } from '../lib/auth'

interface ChatOption {
  label: string
  value: string
}

interface QuestionItem {
  question_id: string
  text: string
  options: ChatOption[]
}

interface QuestionBatchMessage {
  type: 'question_batch'
  questions: QuestionItem[]
}

interface MatchReason {
  criterion: string
  status: string
  evidence: string | null
  confirmed: boolean
  conflicting: boolean
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

type ServerMessage = QuestionBatchMessage | ResultMessage | ErrorMessage
type ConnectionStatus = 'connecting' | 'open' | 'closed'

const WS_BASE = API_BASE.replace(/^http/, 'ws')
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000]

function getSessionId(companyId: string, policyId: string | null): string {
  // Scoped per target policy so opening chat from a different recommendation
  // card starts a fresh clarification round instead of resuming/colliding
  // with a session already focused on (or completed for) another policy.
  const key = policyId ? `chat_session_id:${companyId}:${policyId}` : `chat_session_id:${companyId}`
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

function scoreBadgeClass(score: number): string {
  if (score >= 70) return 'badge-success'
  if (score >= 40) return 'badge-warning'
  return 'badge-error'
}

function reasonBadgeClass(reason: MatchReason): string {
  if (reason.status === '충족') return 'badge-success'
  if (reason.status === '미충족') {
    if (reason.confirmed) return 'badge-error'
    if (reason.conflicting) return 'badge-info'
    return 'badge-warning'
  }
  return 'badge-neutral'
}

function reasonStatusLabel(reason: MatchReason): string {
  if (reason.status === '미충족') {
    if (reason.confirmed) return '미충족 확정'
    if (reason.conflicting) return '미충족 (답변과 다름)'
  }
  return reason.status
}

export default function ChatPage() {
  const { companyId, token } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const policyId = searchParams.get('policy_id')
  const policyTitle = searchParams.get('title')
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [questions, setQuestions] = useState<QuestionItem[] | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [answeredHistory, setAnsweredHistory] = useState<{ text: string; answerLabel: string }[]>([])
  const [waitingPhase, setWaitingPhase] = useState<'checking' | 'recalculating'>('checking')
  const [result, setResult] = useState<ChatMatch[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const startedRef = useRef(false)
  const sessionIdRef = useRef<string | null>(companyId ? getSessionId(companyId, policyId) : null)
  const focusMatch = result?.find((match) => match.policy_id === policyId) ?? null
  const otherMatches = result ? result.filter((match) => match.policy_id !== policyId) : []

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
        ws.send(
          JSON.stringify({
            type: 'start',
            company_id: companyId,
            ...(policyId ? { policy_id: policyId } : {}),
          }),
        )
      }
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as ServerMessage
      if (data.type === 'question_batch') {
        setQuestions(data.questions)
        setAnswers({})
        setResult(null)
        setError(null)
      } else if (data.type === 'result') {
        setResult(data.matches)
        setQuestions(null)
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
  }, [companyId, token, policyId])

  useEffect(() => {
    // Navigating between recommendation cards keeps this component mounted but
    // changes `policyId` -- switch to that policy's own session before the
    // connect effect below tears down and re-opens the socket.
    if (!companyId) return
    sessionIdRef.current = getSessionId(companyId, policyId)
    startedRef.current = false
    setQuestions(null)
    setAnswers({})
    setAnsweredHistory([])
    setWaitingPhase('checking')
    setResult(null)
    setError(null)
  }, [companyId, policyId])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  function selectAnswer(questionId: string, value: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: value }))
  }

  function submitAnswers() {
    if (!questions || wsRef.current?.readyState !== WebSocket.OPEN) return
    const payload = questions.map((q) => ({ question_id: q.question_id, value: answers[q.question_id] }))
    const historyEntries = questions.map((q) => ({
      text: q.text,
      answerLabel: q.options.find((opt) => opt.value === answers[q.question_id])?.label ?? answers[q.question_id],
    }))
    setAnsweredHistory((prev) => [...prev, ...historyEntries])
    wsRef.current.send(JSON.stringify({ type: 'answer_batch', answers: payload }))
    setQuestions(null)
    setAnswers({})
    setWaitingPhase('recalculating')
  }

  function restart() {
    if (!companyId) return
    const key = policyId ? `chat_session_id:${companyId}:${policyId}` : `chat_session_id:${companyId}`
    localStorage.removeItem(key)
    sessionIdRef.current = getSessionId(companyId, policyId)
    startedRef.current = false
    setQuestions(null)
    setAnswers({})
    setAnsweredHistory([])
    setWaitingPhase('checking')
    setResult(null)
    setError(null)
    wsRef.current?.close()
  }

  return (
    <main className="mx-auto max-w-lg px-4 py-8">
      <h1 className="mb-4 text-2xl font-semibold text-base-content">맞춤 상담 채팅</h1>
      {policyTitle && (
        <p className="mb-4 rounded-box border border-base-300 bg-base-100 px-4 py-2.5 text-sm">
          <strong className="text-base-content">{policyTitle}</strong> 정책에 대해 질문에 답하고 재계산합니다.
        </p>
      )}
      <p className="mb-4 text-xs text-base-content/60">연결 상태: {statusLabel(status)}</p>
      {error && <p className="mb-4 text-sm text-error">{error}</p>}
      {!result && answeredHistory.length > 0 && (
        <div className="mb-4 flex flex-col gap-2">
          {answeredHistory.map((h, i) => (
            <div key={i} className="card border border-base-300 bg-base-100 opacity-70">
              <div className="card-body gap-2 py-3">
                <p className="whitespace-pre-line text-sm text-base-content">{h.text}</p>
                <span className="badge badge-neutral badge-sm w-fit">답변: {h.answerLabel}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {questions && questions.length > 0 && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-base-content/70">
            {answeredHistory.length > 0
              ? `추가로 확인이 필요한 질문 ${questions.length}개에 답한 뒤 제출해주세요.`
              : `아래 ${questions.length}개 질문에 모두 답한 뒤 제출해주세요.`}
          </p>
          {questions.map((q) => (
            <div key={q.question_id} className="card border border-base-300 bg-base-100">
              <div className="card-body gap-4">
                <p className="whitespace-pre-line text-sm text-base-content">{q.text}</p>
                <div className="flex gap-3">
                  {q.options.map((opt) => (
                    <button
                      key={opt.value}
                      className={`btn btn-sm ${
                        answers[q.question_id] === opt.value ? 'btn-primary' : 'btn-outline btn-primary'
                      }`}
                      onClick={() => selectAnswer(q.question_id, opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ))}
          <button
            className="btn btn-primary self-start"
            disabled={questions.some((q) => !answers[q.question_id])}
            onClick={submitAnswers}
          >
            답변 제출 ({Object.keys(answers).length}/{questions.length})
          </button>
        </div>
      )}
      {result && (
        <div>
          {focusMatch && (
            <div className="mb-6">
              <h2 className="mb-3 mt-2 text-lg font-semibold text-base-content">
                {policyTitle ?? focusMatch.title} 매칭 결과
              </h2>
              <div className="card border border-primary bg-base-100">
                <div className="card-body gap-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-base-content">{focusMatch.title}</span>
                    <span className={`badge ${scoreBadgeClass(focusMatch.score)} shrink-0 font-semibold`}>
                      {focusMatch.score}점
                    </span>
                  </div>
                  <ul className="flex flex-col gap-2.5 border-t border-base-300 pt-3">
                    {focusMatch.reasons.map((reason, i) => (
                      <li key={i} className="text-sm">
                        <span className={`badge badge-sm ${reasonBadgeClass(reason)} mr-2`}>
                          {reasonStatusLabel(reason)}
                        </span>
                        <span>{reason.criterion}</span>
                        {reason.evidence && <p className="mt-1 text-xs text-base-content/60">{reason.evidence}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
          {otherMatches.length > 0 && (
            <>
              <h2 className="mb-3 mt-2 text-lg font-semibold text-base-content">
                {focusMatch ? '다른 추천 정책' : '매칭 결과'}
              </h2>
              <ul className="flex flex-col gap-3">
                {otherMatches.map((match) => (
                  <li key={match.policy_id} className="card border border-base-300 bg-base-100">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left"
                      title="클릭하면 이 정책으로 상담을 이어갑니다"
                      onClick={() =>
                        navigate(
                          `/chat?policy_id=${encodeURIComponent(match.policy_id)}&title=${encodeURIComponent(match.title)}`,
                        )
                      }
                    >
                      <span className="font-medium text-base-content">{match.title}</span>
                      <span className={`badge ${scoreBadgeClass(match.score)} shrink-0 font-semibold`}>
                        {match.score}점
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="mt-4 flex items-center gap-4">
            <button className="btn btn-outline btn-sm" onClick={restart}>
              새 상담 시작
            </button>
            <Link to="/" className="link link-primary text-sm">
              대시보드로 돌아가기
            </Link>
          </div>
        </div>
      )}
      {!questions && !result && status === 'open' && (
        <div>
          <p className="mb-3 flex items-center gap-2 text-base-content/70">
            <span className="loading loading-spinner loading-xs" />
            {waitingPhase === 'checking'
              ? '확인할 질문이 있는지 확인하는 중입니다...'
              : '답변을 반영해서 재계산하는 중입니다... (수십 초 소요될 수 있음)'}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-base-300">
            <div className="indeterminate-bar h-full w-1/3 rounded-full bg-primary" />
          </div>
        </div>
      )}
    </main>
  )
}
