import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { apiFetch } from './api'

interface AuthState {
  token: string | null
  companyId: string | null
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

interface LoginResponse {
  access_token: string
  token_type: string
  company_id: string
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readInitialState(): AuthState {
  return {
    token: localStorage.getItem('access_token'),
    companyId: localStorage.getItem('company_id'),
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(readInitialState)

  useEffect(() => {
    function handleUnauthorized() {
      setState({ token: null, companyId: null })
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized)
  }, [])

  async function login(email: string, password: string) {
    const data = await apiFetch<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
      skipAuth: true,
    })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('company_id', data.company_id)
    setState({ token: data.access_token, companyId: data.company_id })
  }

  function logout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('company_id')
    setState({ token: null, companyId: null })
  }

  return <AuthContext.Provider value={{ ...state, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  const location = useLocation()
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}
