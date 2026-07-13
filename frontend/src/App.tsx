import { NavLink, Route, Routes } from 'react-router-dom'
import { RequireAuth, useAuth } from './lib/auth'
import ChatPage from './pages/ChatPage'
import DashboardPage from './pages/DashboardPage'
import GraphPage from './pages/GraphPage'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return `rounded-btn px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? 'bg-primary/15 text-primary' : 'text-base-content/70 hover:bg-base-200 hover:text-base-content'
  }`
}

function NavBar() {
  const { token, companyId, logout } = useAuth()
  if (!token) return null

  return (
    <nav className="navbar border-b border-base-300 bg-base-100 px-4">
      <div className="flex-1">
        <span className="text-lg font-semibold text-base-content">기업지원 종합 사이트</span>
      </div>
      <div className="flex flex-none items-center gap-1">
        <NavLink to="/" end className={navLinkClass}>
          매칭 대시보드
        </NavLink>
        <NavLink to="/chat" className={navLinkClass}>
          채팅 상담
        </NavLink>
        <NavLink to="/graph" className={navLinkClass}>
          정책 그래프
        </NavLink>
        <NavLink to="/profile" className={navLinkClass}>
          기업 정보
        </NavLink>
      </div>
      <div className="ml-4 flex flex-none items-center gap-3 border-l border-base-300 pl-4 text-sm">
        <span className="text-base-content/70">{companyId}</span>
        <button className="btn btn-ghost btn-sm" onClick={logout}>
          로그아웃
        </button>
      </div>
    </nav>
  )
}

function App() {
  return (
    <div className="min-h-svh bg-base-200/40">
      <NavBar />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <DashboardPage />
            </RequireAuth>
          }
        />
        <Route
          path="/chat"
          element={
            <RequireAuth>
              <ChatPage />
            </RequireAuth>
          }
        />
        <Route
          path="/graph"
          element={
            <RequireAuth>
              <GraphPage />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <ProfilePage />
            </RequireAuth>
          }
        />
      </Routes>
    </div>
  )
}

export default App
