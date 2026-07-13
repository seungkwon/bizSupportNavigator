"""Matching endpoints (detailed_plan.md 8): `/matches` (read cached results) and
`/matches/refresh` (recompute via the full LangGraph pipeline -- meta_filter ->
rag_search -> graph_reasoning -> llm_judge -> score_aggregate, then persist to
`match_results`). `/policy-candidates` is the lighter Milestone 4/5 debug endpoint
(vector-ranked candidates + graph evidence, no LLM judging/scoring/cost).

All three are company-scoped (detailed_plan.md 6): `require_company_scope`
checks the bearer JWT's company against the `company_id` path param, so one
company can't read another's data by guessing IDs in the URL.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_company_scope
from app.db.postgres import get_db
from app.models.policy import Policy
from app.services.company_profile import get_company_demographics
from app.services.match_results import list_match_results, save_match_results
from app.services.orchestrator import run_full_matching, run_policy_matching

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


class MatchReasonOut(BaseModel):
    criterion: str
    status: str
    evidence: str | None
    confirmed: bool = False


class MatchResultOut(BaseModel):
    policy_id: str
    title: str
    score: int
    reasons: list[MatchReasonOut]
    computed_at: datetime


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
    _: str = Depends(require_company_scope),
) -> list[PolicyCandidateOut]:
    company = get_company_demographics(db, company_id)
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


@router.post("/{company_id}/matches/refresh", response_model=list[MatchResultOut])
def refresh_matches(
    company_id: str,
    query: str | None = Query(default=None, description="비어 있으면 기업 프로필로 자동 생성"),
    limit: int = Query(default=5, ge=1, le=50),
    only_open: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> list[MatchResultOut]:
    company = get_company_demographics(db, company_id)
    query_text = query or _default_query_text(company)
    scored_matches = run_full_matching(db, company, query_text, limit=limit, only_open=only_open)
    computed_at = save_match_results(db, company_id, scored_matches)
    return [
        MatchResultOut(
            policy_id=match.policy_id,
            title=match.title,
            score=match.score,
            reasons=[MatchReasonOut(**vars(reason)) for reason in match.reasons],
            computed_at=computed_at,
        )
        for match in scored_matches
    ]


@router.get("/{company_id}/matches", response_model=list[MatchResultOut])
def get_matches(
    company_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> list[MatchResultOut]:
    results = list_match_results(db, company_id)
    titles = {
        policy.policy_id: policy.title
        for policy in db.execute(
            select(Policy).where(Policy.policy_id.in_([r.policy_id for r in results]))
        ).scalars()
    }
    return [
        MatchResultOut(
            policy_id=result.policy_id,
            title=titles.get(result.policy_id, result.policy_id),
            score=result.score,
            reasons=[MatchReasonOut(**reason) for reason in result.reasons],
            computed_at=result.computed_at,
        )
        for result in results
    ]
