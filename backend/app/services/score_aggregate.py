"""Milestone 6 score_aggregate (detailed_plan.md 4.5 step 6 / 4.6 schema): turns
per-criterion judgments into a single 0-100 score plus the `reasons` list.

Eligibility and exclusion judgments are averaged *separately* and then combined
with a fixed 70/30 weighting, rather than one flat average over every criterion.
A flat average was tried first and produces an obviously wrong ranking: a policy
with 2 eligibility criteria (both 미충족 -- the company doesn't qualify at all)
and 9 exclusion criteria (all 충족, i.e. not disqualified) averaged to 82/100,
because the many "not excluded" criteria drowned out the two failed eligibility
gates. Eligibility criteria are the "do you even qualify" gate and should
dominate; exclusion criteria are disqualifying edge cases. On top of the 70/30
blend, one hard rule remains: a confirmed exclusion match -- 미충족 on a criterion
reframed as "이 제외요건에 해당하지 않음" (app/services/llm_judge.py), i.e. the
company DOES match an exclusion condition -- caps the score at 0 regardless of
the eligibility score, since exclusion clauses are typically absolute.
"""

from dataclasses import dataclass

from app.services.llm_judge import CriterionJudgment

_WEIGHTS = {"충족": 1.0, "정보부족": 0.5, "미충족": 0.0}
_ELIGIBILITY_WEIGHT = 0.7
_EXCLUSION_WEIGHT = 0.3


@dataclass
class MatchReason:
    criterion: str
    status: str
    evidence: str | None
    # True when a 미충족 judgment was directly confirmed by the user answering
    # a chat question ("아니오"), not just inferred by the LLM from RAG
    # evidence -- app/services/chat_service.py sets this after scoring, since
    # it needs the company's fact history to know. Always False for 충족/정보부족.
    confirmed: bool = False


@dataclass
class ScoredMatch:
    policy_id: str
    title: str
    score: int
    reasons: list[MatchReason]


def _group_average(judgments: list[CriterionJudgment]) -> float | None:
    if not judgments:
        return None
    return sum(_WEIGHTS[j.status] for j in judgments) / len(judgments)


def aggregate_score(policy_id: str, title: str, judgments: list[CriterionJudgment]) -> ScoredMatch:
    if not judgments:
        return ScoredMatch(policy_id=policy_id, title=title, score=0, reasons=[])

    eligibility = [j for j in judgments if not j.is_exclusion]
    exclusion = [j for j in judgments if j.is_exclusion]
    excluded = any(j.status == "미충족" for j in exclusion)

    eligibility_avg = _group_average(eligibility)
    exclusion_avg = _group_average(exclusion)
    if eligibility_avg is None:
        raw_score = exclusion_avg * 100 if exclusion_avg is not None else 0.0
    elif exclusion_avg is None:
        raw_score = eligibility_avg * 100
    else:
        raw_score = (eligibility_avg * _ELIGIBILITY_WEIGHT + exclusion_avg * _EXCLUSION_WEIGHT) * 100
    score = 0 if excluded else round(raw_score)

    reasons = [MatchReason(criterion=j.criterion, status=j.status, evidence=j.evidence) for j in judgments]
    return ScoredMatch(policy_id=policy_id, title=title, score=score, reasons=reasons)
