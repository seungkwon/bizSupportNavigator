import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { apiFetch, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'

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

interface CompanyFact {
  id: number
  criterion_text: string
  answer: string
  source_policy_id: string | null
  created_at: string
}

type ProfileForm = Omit<CompanyProfile, 'company_id' | 'raw_business_plan'> & { business_summary: string }

function toForm(profile: CompanyProfile): ProfileForm {
  const { company_id: _companyId, raw_business_plan, ...rest } = profile
  return { ...rest, business_summary: raw_business_plan.summary ?? '' }
}

export default function ProfilePage() {
  const { companyId } = useAuth()
  const [form, setForm] = useState<ProfileForm | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)

  const [facts, setFacts] = useState<CompanyFact[]>([])
  const [factsError, setFactsError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState<{ criterion_text: string; answer: string }>({
    criterion_text: '',
    answer: '예',
  })
  const [newFact, setNewFact] = useState<{ criterion_text: string; answer: string }>({
    criterion_text: '',
    answer: '예',
  })

  useEffect(() => {
    if (!companyId) return
    apiFetch<CompanyProfile>(`/internal/companies/${companyId}/demographics`)
      .then((profile) => setForm(toForm(profile)))
      .catch((err) => setProfileError(err instanceof ApiError ? err.message : '프로필을 불러오지 못했습니다'))
  }, [companyId])

  const loadFacts = useCallback(async () => {
    if (!companyId) return
    try {
      setFacts(await apiFetch<CompanyFact[]>(`/api/companies/${companyId}/facts`))
    } catch (err) {
      setFactsError(err instanceof ApiError ? err.message : '저장된 정보를 불러오지 못했습니다')
    }
  }, [companyId])

  useEffect(() => {
    void loadFacts()
  }, [loadFacts])

  async function handleProfileSubmit(event: FormEvent) {
    event.preventDefault()
    if (!companyId || !form) return
    setProfileSaving(true)
    setProfileError(null)
    setProfileSaved(false)
    try {
      const { business_summary, ...rest } = form
      const updated = await apiFetch<CompanyProfile>(`/internal/companies/${companyId}/demographics`, {
        method: 'PUT',
        body: JSON.stringify({ ...rest, raw_business_plan: { summary: business_summary } }),
      })
      setForm(toForm(updated))
      setProfileSaved(true)
    } catch (err) {
      setProfileError(err instanceof ApiError ? err.message : '저장에 실패했습니다')
    } finally {
      setProfileSaving(false)
    }
  }

  function updateField<K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  async function handleAddFact(event: FormEvent) {
    event.preventDefault()
    if (!companyId || !newFact.criterion_text.trim()) return
    setFactsError(null)
    try {
      await apiFetch(`/api/companies/${companyId}/facts`, { method: 'POST', body: JSON.stringify(newFact) })
      setNewFact({ criterion_text: '', answer: '예' })
      await loadFacts()
    } catch (err) {
      setFactsError(err instanceof ApiError ? err.message : '추가에 실패했습니다')
    }
  }

  function startEdit(fact: CompanyFact) {
    setEditingId(fact.id)
    setEditDraft({ criterion_text: fact.criterion_text, answer: fact.answer })
  }

  async function saveEdit(factId: number) {
    if (!companyId) return
    setFactsError(null)
    try {
      await apiFetch(`/api/companies/${companyId}/facts/${factId}`, {
        method: 'PUT',
        body: JSON.stringify(editDraft),
      })
      setEditingId(null)
      await loadFacts()
    } catch (err) {
      setFactsError(err instanceof ApiError ? err.message : '수정에 실패했습니다')
    }
  }

  async function deleteFact(factId: number) {
    if (!companyId) return
    setFactsError(null)
    try {
      await apiFetch(`/api/companies/${companyId}/facts/${factId}`, { method: 'DELETE' })
      await loadFacts()
    } catch (err) {
      setFactsError(err instanceof ApiError ? err.message : '삭제에 실패했습니다')
    }
  }

  return (
    <main className="page">
      <div className="page-header">
        <h1>기업 정보 관리</h1>
      </div>

      {form && (
        <form className="form-card" onSubmit={handleProfileSubmit}>
          <label>
            기업명
            <input value={form.company_name} onChange={(e) => updateField('company_name', e.target.value)} required />
          </label>
          <label>
            사업자등록번호
            <input
              value={form.biz_registration_no}
              onChange={(e) => updateField('biz_registration_no', e.target.value)}
              required
            />
          </label>
          <label>
            지역
            <input value={form.region} onChange={(e) => updateField('region', e.target.value)} required />
          </label>
          <label>
            기업규모
            <input value={form.company_size} onChange={(e) => updateField('company_size', e.target.value)} required />
          </label>
          <label>
            업종코드
            <input value={form.industry_code} onChange={(e) => updateField('industry_code', e.target.value)} required />
          </label>
          <label>
            설립일
            <input
              type="date"
              value={form.established_date}
              onChange={(e) => updateField('established_date', e.target.value)}
              required
            />
          </label>
          <label>
            종업원수
            <input
              type="number"
              min={0}
              value={form.employee_count}
              onChange={(e) => updateField('employee_count', Number(e.target.value))}
              required
            />
          </label>
          <label>
            연매출(원)
            <input
              type="number"
              min={0}
              value={form.annual_revenue}
              onChange={(e) => updateField('annual_revenue', Number(e.target.value))}
              required
            />
          </label>
          <label>
            사업계획 요약
            <input
              value={form.business_summary}
              onChange={(e) => updateField('business_summary', e.target.value)}
            />
          </label>
          {profileError && <p className="error-text">{profileError}</p>}
          {profileSaved && <p className="hint">저장되었습니다.</p>}
          <button type="submit" disabled={profileSaving}>
            {profileSaving ? '저장 중...' : '프로필 저장'}
          </button>
        </form>
      )}

      <h2 className="graph-subtitle section-spaced">채팅으로 수집된 기업 정보</h2>
      <p className="hint">
        채팅 상담 중 답변한 내용이 여기 저장되며, 다른 정책을 검토할 때도 비슷한 요건이면 다시 묻지 않고 재사용됩니다.
        틀린 내용은 직접 수정하거나 삭제할 수 있습니다.
      </p>
      {factsError && <p className="error-text">{factsError}</p>}

      <ul className="match-list">
        {facts.map((fact) => (
          <li key={fact.id} className="match-card">
            {editingId === fact.id ? (
              <div className="fact-edit-row">
                <input
                  value={editDraft.criterion_text}
                  onChange={(e) => setEditDraft((prev) => ({ ...prev, criterion_text: e.target.value }))}
                />
                <select
                  value={editDraft.answer}
                  onChange={(e) => setEditDraft((prev) => ({ ...prev, answer: e.target.value }))}
                >
                  <option value="예">예</option>
                  <option value="아니오">아니오</option>
                </select>
                <button onClick={() => saveEdit(fact.id)}>저장</button>
                <button onClick={() => setEditingId(null)}>취소</button>
              </div>
            ) : (
              <div className="fact-row">
                <span className="fact-text">{fact.criterion_text}</span>
                <span className={`score-badge ${fact.answer === '예' ? 'score-high' : 'score-low'}`}>
                  {fact.answer}
                </span>
                <button onClick={() => startEdit(fact)}>수정</button>
                <button onClick={() => deleteFact(fact.id)}>삭제</button>
              </div>
            )}
          </li>
        ))}
        {facts.length === 0 && <p>아직 저장된 정보가 없습니다.</p>}
      </ul>

      <form className="form-card" style={{ marginTop: 16 }} onSubmit={handleAddFact}>
        <label>
          새 항목 직접 추가
          <input
            value={newFact.criterion_text}
            onChange={(e) => setNewFact((prev) => ({ ...prev, criterion_text: e.target.value }))}
            placeholder="예: 설립일이 3년 이내이다"
          />
        </label>
        <label>
          답변
          <select
            value={newFact.answer}
            onChange={(e) => setNewFact((prev) => ({ ...prev, answer: e.target.value }))}
          >
            <option value="예">예</option>
            <option value="아니오">아니오</option>
          </select>
        </label>
        <button type="submit">추가</button>
      </form>
    </main>
  )
}
