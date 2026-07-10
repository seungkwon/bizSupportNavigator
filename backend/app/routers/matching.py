"""Milestone 4 candidate-search endpoint (detailed_plan.md 4.4/4.5 steps 1-3).

No LangGraph orchestration, scoring, or clarification-question flow yet -- those
are `llm_judge`/`score_aggregate`/`ask_clarification` (Milestone 6), wired through
the full `/matches` API (detailed_plan.md 8) once section 4.5 lands end to end.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.mock.demographics import get_company_demographics
from app.services.matching import search_policy_candidates

router = APIRouter(prefix="/api/companies", tags=["matching"])


class MatchedChunkOut(BaseModel):
    chunk_id: str
    section_title: str | None
    content: str
    distance: float


class PolicyCandidateOut(BaseModel):
    policy_id: str
    title: str
    best_distance: float
    matched_chunks: list[MatchedChunkOut]


def _default_query_text(company) -> str:
    summary = company.raw_business_plan.get("summary", "")
    return (
        f"기업규모: {company.company_size}, 지역: {company.region}, "
        f"업종코드: {company.industry_code}, 사업계획: {summary}"
    )


@router.get("/{company_id}/policy-candidates", response_model=list[PolicyCandidateOut])
def get_policy_candidates(
    company_id: str,
    query: str | None = Query(default=None, description="비어 있으면 기업 프로필로 자동 생성"),
    limit: int = Query(default=10, ge=1, le=50),
    only_open: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> list[PolicyCandidateOut]:
    company = get_company_demographics(company_id)
    query_text = query or _default_query_text(company)
    candidates = search_policy_candidates(db, query_text, limit=limit, only_open=only_open)
    return [
        PolicyCandidateOut(
            policy_id=c.policy_id,
            title=c.title,
            best_distance=c.best_distance,
            matched_chunks=[MatchedChunkOut(**vars(chunk)) for chunk in c.matched_chunks],
        )
        for c in candidates
    ]
