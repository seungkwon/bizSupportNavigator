"""Candidate-search endpoint running the LangGraph orchestrator (detailed_plan.md
4.5 steps 1-4: load_company_profile (here, via the mock adapter) -> meta_filter ->
rag_search -> graph_reasoning). Scoring/clarification (`llm_judge`,
`score_aggregate`, `ask_clarification`) are Milestone 6, wired through the full
`/matches` API (detailed_plan.md 8) once those land.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.mock.demographics import get_company_demographics
from app.services.orchestrator import run_policy_matching

router = APIRouter(prefix="/api/companies", tags=["matching"])


class MatchedChunkOut(BaseModel):
    chunk_id: str
    section_title: str | None
    content: str
    distance: float


class GraphCriterionOut(BaseModel):
    description: str
    company_attribute: str | None


class PolicyCandidateOut(BaseModel):
    policy_id: str
    title: str
    best_distance: float
    matched_chunks: list[MatchedChunkOut]
    eligibility_criteria: list[GraphCriterionOut]
    exclusion_criteria: list[GraphCriterionOut]


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
    candidates, graph_evidence = run_policy_matching(db, query_text, limit=limit, only_open=only_open)

    results = []
    for candidate in candidates:
        evidence = graph_evidence.get(candidate.policy_id)
        results.append(
            PolicyCandidateOut(
                policy_id=candidate.policy_id,
                title=candidate.title,
                best_distance=candidate.best_distance,
                matched_chunks=[MatchedChunkOut(**vars(chunk)) for chunk in candidate.matched_chunks],
                eligibility_criteria=[
                    GraphCriterionOut(**vars(c)) for c in (evidence.eligibility_criteria if evidence else [])
                ],
                exclusion_criteria=[
                    GraphCriterionOut(**vars(c)) for c in (evidence.exclusion_criteria if evidence else [])
                ],
            )
        )
    return results
