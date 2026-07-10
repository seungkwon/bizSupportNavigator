"""Reads/writes cached matching results (detailed_plan.md 4.6/7/8 `match_results`).

`/matches/refresh` recomputes via app/services/orchestrator.py and calls
`save_match_results`; `/matches` reads back via `list_match_results` without
re-running the LLM/graph pipeline.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.match_result import MatchResult
from app.services.score_aggregate import ScoredMatch


def save_match_results(db: Session, company_id: str, scored_matches: list[ScoredMatch]) -> datetime:
    now = datetime.now(timezone.utc)
    for match in scored_matches:
        reasons_json = [
            {"criterion": reason.criterion, "status": reason.status, "evidence": reason.evidence}
            for reason in match.reasons
        ]
        existing = db.execute(
            select(MatchResult).where(
                MatchResult.company_id == company_id, MatchResult.policy_id == match.policy_id
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                MatchResult(
                    company_id=company_id,
                    policy_id=match.policy_id,
                    score=match.score,
                    reasons=reasons_json,
                    computed_at=now,
                )
            )
        else:
            existing.score = match.score
            existing.reasons = reasons_json
            existing.computed_at = now
    db.commit()
    return now


def list_match_results(db: Session, company_id: str) -> list[MatchResult]:
    return list(
        db.execute(
            select(MatchResult)
            .where(MatchResult.company_id == company_id)
            .order_by(MatchResult.score.desc())
        ).scalars()
    )
