import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

interface MatchReason {
  criterion: string
  status: string
  evidence: string | null
  confirmed: boolean
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

function scoreBadgeClass(score: number): string {
  if (score >= 70) return 'badge-success'
  if (score >= 40) return 'badge-warning'
  return 'badge-error'
}

function reasonBadgeClass(reason: MatchReason): string {
  if (reason.status === '충족') return 'badge-success'
  if (reason.status === '미충족') return reason.confirmed ? 'badge-error' : 'badge-warning'
  return 'badge-neutral'
}

function reasonStatusLabel(reason: MatchReason): string {
  if (reason.status === '미충족' && reason.confirmed) return '미충족 확정'
  return reason.status
}

function ProfileCard({ profile }: { profile: CompanyProfile }) {
  return (
    <div className="card mb-6 border border-base-300 bg-base-100">
      <div className="card-body gap-4">
        <div className="flex items-baseline gap-3">
          <h2 className="text-lg font-semibold text-base-content">{profile.company_name}</h2>
          <span className="text-sm text-base-content/60">{profile.biz_registration_no}</span>
        </div>
        <dl className="grid grid-cols-2 gap-x-5 gap-y-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-base-content/60">지역</dt>
            <dd className="mt-0.5 text-sm font-medium">{profile.region}</dd>
          </div>
          <div>
            <dt className="text-xs text-base-content/60">기업규모</dt>
            <dd className="mt-0.5 text-sm font-medium">{profile.company_size}</dd>
          </div>
          <div>
            <dt className="text-xs text-base-content/60">업종코드</dt>
            <dd className="mt-0.5 text-sm font-medium">{profile.industry_code}</dd>
          </div>
          <div>
            <dt className="text-xs text-base-content/60">설립일</dt>
            <dd className="mt-0.5 text-sm font-medium">{profile.established_date}</dd>
          </div>
          <div>
            <dt className="text-xs text-base-content/60">종업원수</dt>
            <dd className="mt-0.5 text-sm font-medium">{profile.employee_count.toLocaleString('ko-KR')}명</dd>
          </div>
          <div>
            <dt className="text-xs text-base-content/60">연매출</dt>
            <dd className="mt-0.5 text-sm font-medium">{profile.annual_revenue.toLocaleString('ko-KR')}원</dd>
          </div>
        </dl>
        {profile.raw_business_plan?.summary && (
          <p className="border-t border-base-300 pt-3 text-sm text-base-content/70">
            {profile.raw_business_plan.summary}
          </p>
        )}
      </div>
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
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-base-content">매칭 대시보드</h1>
        <button className="btn btn-primary btn-sm" onClick={handleRefresh} disabled={refreshing}>
          {refreshing && <span className="loading loading-spinner loading-xs" />}
          {refreshing ? '재계산 중...' : '다시 계산'}
        </button>
      </div>
      {refreshing && (
        <div className="mb-6 h-1.5 w-full overflow-hidden rounded-full bg-base-300">
          <div className="indeterminate-bar h-full w-1/3 rounded-full bg-primary" />
        </div>
      )}
      {profile && <ProfileCard profile={profile} />}
      {error && <p className="mb-4 text-sm text-error">{error}</p>}
      {loading ? (
        <p className="text-base-content/70">불러오는 중...</p>
      ) : matches.length === 0 ? (
        <p className="text-base-content/70">매칭 결과가 없습니다. &quot;다시 계산&quot;을 눌러 계산해보세요.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {matches.map((match) => (
            <li key={match.policy_id} className="card overflow-hidden border border-base-300 bg-base-100">
              <div className="flex w-full items-center gap-3 px-4 py-3.5">
                <label className="flex flex-1 cursor-pointer items-center gap-3" title="체크하면 이 정책에 대한 질문 답변 채팅으로 이동합니다">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-primary checkbox-sm shrink-0"
                    onChange={() =>
                      navigate(
                        `/chat?policy_id=${encodeURIComponent(match.policy_id)}&title=${encodeURIComponent(match.title)}`,
                      )
                    }
                  />
                  <button
                    type="button"
                    className="flex-1 text-left font-medium text-base-content"
                    onClick={() => setExpanded(expanded === match.policy_id ? null : match.policy_id)}
                  >
                    {match.title}
                  </button>
                </label>
                <span className={`badge ${scoreBadgeClass(match.score)} shrink-0 font-semibold`}>
                  {match.score}점
                </span>
              </div>
              {expanded === match.policy_id && (
                <ul className="flex flex-col gap-2.5 border-t border-base-300 px-4 pb-4 pt-3">
                  {match.reasons.map((reason, i) => (
                    <li key={i} className="pt-2 text-sm first:pt-0">
                      <span className={`badge badge-sm ${reasonBadgeClass(reason)} mr-2`}>
                        {reasonStatusLabel(reason)}
                      </span>
                      <span>{reason.criterion}</span>
                      {reason.evidence && <p className="mt-1 text-xs text-base-content/60">{reason.evidence}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
