import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

interface MatchReason {
  criterion: string
  status: string
  evidence: string | null
}

interface MatchResult {
  policy_id: string
  title: string
  score: number
  reasons: MatchReason[]
  computed_at: string
}

interface CompanyProfile {
  company_id: string
  company_name: string
  biz_registration_no: string
  region: string
  company_size: string
  industry_code: string
  established_date: string
  employee_count: number
  annual_revenue: number
  raw_business_plan: { summary?: string }
}

function scoreTier(score: number): 'high' | 'mid' | 'low' {
  if (score >= 70) return 'high'
  if (score >= 40) return 'mid'
  return 'low'
}

function ProfileCard({ profile }: { profile: CompanyProfile }) {
  return (
    <div className="profile-card">
      <div className="profile-card-header">
        <h2>{profile.company_name}</h2>
        <span className="profile-reg-no">{profile.biz_registration_no}</span>
      </div>
      <dl className="profile-grid">
        <div>
          <dt>지역</dt>
          <dd>{profile.region}</dd>
        </div>
        <div>
          <dt>기업규모</dt>
          <dd>{profile.company_size}</dd>
        </div>
        <div>
          <dt>업종코드</dt>
          <dd>{profile.industry_code}</dd>
        </div>
        <div>
          <dt>설립일</dt>
          <dd>{profile.established_date}</dd>
        </div>
        <div>
          <dt>종업원수</dt>
          <dd>{profile.employee_count.toLocaleString('ko-KR')}명</dd>
        </div>
        <div>
          <dt>연매출</dt>
          <dd>{profile.annual_revenue.toLocaleString('ko-KR')}원</dd>
        </div>
      </dl>
      {profile.raw_business_plan?.summary && (
        <p className="profile-summary">{profile.raw_business_plan.summary}</p>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const { companyId } = useAuth()
  const navigate = useNavigate()
  const [profile, setProfile] = useState<CompanyProfile | null>(null)
  const [matches, setMatches] = useState<MatchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    if (!companyId) return
    apiFetch<CompanyProfile>(`/internal/companies/${companyId}/demographics`)
      .then(setProfile)
      .catch(() => setProfile(null))
  }, [companyId])

  const loadMatches = useCallback(async () => {
    if (!companyId) return
    setLoading(true)
    setError(null)
    try {
      setMatches(await apiFetch<MatchResult[]>(`/api/companies/${companyId}/matches`))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '매칭 결과를 불러오지 못했습니다')
    } finally {
      setLoading(false)
    }
  }, [companyId])

  useEffect(() => {
    void loadMatches()
  }, [loadMatches])

  async function handleRefresh() {
    if (!companyId) return
    setRefreshing(true)
    setError(null)
    try {
      setMatches(
        await apiFetch<MatchResult[]>(`/api/companies/${companyId}/matches/refresh`, { method: 'POST' }),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '재계산에 실패했습니다')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <main className="page">
      <div className="page-header">
        <h1>매칭 대시보드</h1>
        <button onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? '재계산 중... (수십 초 소요될 수 있음)' : '다시 계산'}
        </button>
      </div>
      {profile && <ProfileCard profile={profile} />}
      {error && <p className="error-text">{error}</p>}
      {loading ? (
        <p>불러오는 중...</p>
      ) : matches.length === 0 ? (
        <p>매칭 결과가 없습니다. "다시 계산"을 눌러 계산해보세요.</p>
      ) : (
        <ul className="match-list">
          {matches.map((match) => (
            <li key={match.policy_id} className="match-card">
              <button
                className="match-card-header"
                onClick={() => setExpanded(expanded === match.policy_id ? null : match.policy_id)}
              >
                <span className="match-title">{match.title}</span>
                <span className={`score-badge score-${scoreTier(match.score)}`}>{match.score}점</span>
              </button>
              {expanded === match.policy_id && (
                <>
                  <ul className="reason-list">
                    {match.reasons.map((reason, i) => (
                      <li key={i} className={`reason-item status-${reason.status}`}>
                        <span className="reason-status">{reason.status}</span>
                        <span className="reason-criterion">{reason.criterion}</span>
                        {reason.evidence && <p className="reason-evidence">{reason.evidence}</p>}
                      </li>
                    ))}
                  </ul>
                  <div className="match-card-actions">
                    <button
                      onClick={() =>
                        navigate(
                          `/chat?policy_id=${encodeURIComponent(match.policy_id)}&title=${encodeURIComponent(match.title)}`,
                        )
                      }
                    >
                      이 정책에 대해 질문 답하고 재계산
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
