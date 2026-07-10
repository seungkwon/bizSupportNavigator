"""Milestone 6 llm_judge (detailed_plan.md 4.5 step 5): judges each graph-derived
criterion against the company's profile via OpenAI structured output.

Exclusion criteria are reframed as a positive "이 제외요건에 해당하지 않음" statement
before judging, so eligibility and exclusion criteria share one status vocabulary
(충족/미충족/정보부족) where 충족 always means "good for the company" -- matching
the detailed_plan.md 4.6 example schema, which lists both under a single `reasons`
list.
"""

from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.mock.demographics import CompanyDemographics
from app.services.graph_reasoning import PolicyGraphEvidence
from app.services.matching import PolicyCandidate


@dataclass
class CriterionJudgment:
    criterion: str
    status: str
    evidence: str | None
    is_exclusion: bool


class _JudgedCriterion(BaseModel):
    criterion_id: str
    status: Literal["충족", "미충족", "정보부족"]
    evidence: str | None = None


class _JudgeResult(BaseModel):
    judgments: list[_JudgedCriterion]


def _company_profile_text(company: CompanyDemographics) -> str:
    return (
        f"기업규모: {company.company_size}\n"
        f"지역: {company.region}\n"
        f"업종코드: {company.industry_code}\n"
        f"설립일: {company.established_date}\n"
        f"종업원수: {company.employee_count}\n"
        f"연매출: {company.annual_revenue}\n"
        f"사업계획 요약: {company.raw_business_plan.get('summary', '')}"
    )


def _build_items(evidence: PolicyGraphEvidence) -> list[tuple[str, str, bool]]:
    items: list[tuple[str, str, bool]] = []
    for index, criterion in enumerate(evidence.eligibility_criteria):
        items.append((f"elig:{index}", criterion.description, False))
    for index, criterion in enumerate(evidence.exclusion_criteria):
        items.append((f"excl:{index}", f"{criterion.description}에 해당하지 않음", True))
    return items


def _fallback(items: list[tuple[str, str, bool]]) -> list[CriterionJudgment]:
    return [
        CriterionJudgment(criterion=statement, status="정보부족", evidence=None, is_exclusion=is_excl)
        for _, statement, is_excl in items
    ]


def judge_policy(
    company: CompanyDemographics,
    candidate: PolicyCandidate,
    evidence: PolicyGraphEvidence | None,
) -> list[CriterionJudgment]:
    if evidence is None:
        return []
    items = _build_items(evidence)
    if not items:
        return []

    settings = get_settings()
    if not settings.openai_api_key:
        return _fallback(items)

    client = OpenAI(api_key=settings.openai_api_key)
    criteria_block = "\n".join(f"- [{cid}] {statement}" for cid, statement, _ in items)
    evidence_block = "\n\n".join(chunk.content for chunk in candidate.matched_chunks)

    try:
        completion = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 정부지원사업 신청자격 판정 어시스턴트다. 주어진 기업 프로필과 "
                        "공고문 발췌를 근거로 각 요건 문장이 이 기업 기준으로 충족/미충족/정보부족 "
                        "중 무엇인지 판단하라. 판단 근거가 부족하면 정보부족으로 표시하라."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"[기업 프로필]\n{_company_profile_text(company)}\n\n"
                        f"[공고문 발췌]\n{evidence_block}\n\n"
                        f"[판정할 요건]\n{criteria_block}"
                    ),
                },
            ],
            response_format=_JudgeResult,
        )
    except Exception:  # noqa: BLE001 - external API call, degrade to 정보부족 for all items
        return _fallback(items)

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        return _fallback(items)

    by_id = {judgment.criterion_id: judgment for judgment in parsed.judgments}
    results: list[CriterionJudgment] = []
    for criterion_id, statement, is_excl in items:
        judgment = by_id.get(criterion_id)
        if judgment is None:
            results.append(
                CriterionJudgment(criterion=statement, status="정보부족", evidence=None, is_exclusion=is_excl)
            )
        else:
            results.append(
                CriterionJudgment(
                    criterion=statement,
                    status=judgment.status,
                    evidence=judgment.evidence,
                    is_exclusion=is_excl,
                )
            )
    return results
