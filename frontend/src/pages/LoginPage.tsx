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
    <main className="page page-narrow">
      <h1>로그인</h1>
      <form className="form-card" onSubmit={handleSubmit}>
        <label>
          이메일
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          비밀번호
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="error-text">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? '로그인 중...' : '로그인'}
        </button>
      </form>
      <p className="hint">데모 계정: demo-001@example.com / demo1234</p>
    </main>
  )
}
