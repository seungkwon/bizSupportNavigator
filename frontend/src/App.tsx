import { NavLink, Route, Routes } from 'react-router-dom'
import './App.css'
import { RequireAuth, useAuth } from './lib/auth'
import ChatPage from './pages/ChatPage'
import DashboardPage from './pages/DashboardPage'
import GraphPage from './pages/GraphPage'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'

function NavBar() {
  const { token, companyId, logout } = useAuth()
  if (!token) return null

  return (
    <nav className="navbar">
      <span className="navbar-brand">기업지원 종합 사이트</span>
      <div className="navbar-links">
        <NavLink to="/" end>
          매칭 대시보드
        </NavLink>
        <NavLink to="/chat">채팅 상담</NavLink>
        <NavLink to="/graph">정책 그래프</NavLink>
        <NavLink to="/profile">기업 정보</NavLink>
      </div>
      <div className="navbar-user">
        <span>{companyId}</span>
        <button onClick={logout}>로그아웃</button>
      </div>
    </nav>
  )
}

function App() {
  return (
    <>
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
    </>
  )
}

export default App
