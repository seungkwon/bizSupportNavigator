import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

export default function LoginPage() {
  const { login, token } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('demo-001@example.com')
  const [password, setPassword] = useState('demo1234')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (token) {
    const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/'
    return <Navigate to={from} replace />
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '로그인에 실패했습니다')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-sm flex-col justify-center px-4 py-12">
      <h1 className="mb-6 text-2xl font-semibold text-base-content">로그인</h1>
      <form className="card border border-base-300 bg-base-100 shadow-sm" onSubmit={handleSubmit}>
        <div className="card-body gap-4">
          <label className="fieldset-label flex-col items-start gap-1.5 text-sm">
            이메일
            <input
              type="email"
              className="input w-full"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="fieldset-label flex-col items-start gap-1.5 text-sm">
            비밀번호
            <input
              type="password"
              className="input w-full"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="text-sm text-error">{error}</p>}
          <button type="submit" className="btn btn-primary mt-2" disabled={loading}>
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </div>
      </form>
      <p className="mt-4 text-center text-sm text-base-content/60">데모 계정: demo-001@example.com / demo1234</p>
    </main>
  )
}
