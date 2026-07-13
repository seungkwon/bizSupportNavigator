// "localhost" is deliberately avoided: on this machine Chroma's docker-proxy also
// listens on port 8000 across all interfaces (docker-compose.yml), while uvicorn binds
// only 127.0.0.1:8000 -- a browser resolving "localhost" to ::1 first hits Chroma instead
// of the API (silent CORS failure, confirmed via Playwright while wiring up this client).
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

interface FetchOptions extends RequestInit {
  skipAuth?: boolean
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { skipAuth, headers, ...rest } = options
  const finalHeaders = new Headers(headers)
  finalHeaders.set('Content-Type', 'application/json')
  if (!skipAuth) {
    const token = localStorage.getItem('access_token')
    if (token) finalHeaders.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders })

  if (res.status === 401 && !skipAuth) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('company_id')
    window.dispatchEvent(new Event('auth:unauthorized'))
    throw new ApiError(401, '인증이 만료되었습니다. 다시 로그인해주세요.')
  }

  if (!res.ok) {
    let message = `요청 실패 (${res.status})`
    try {
      const body = await res.json()
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      // response body wasn't JSON -- keep the generic status message
    }
    throw new ApiError(res.status, message)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
