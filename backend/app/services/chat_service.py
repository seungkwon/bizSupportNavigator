"""Milestone 7 chat session orchestration (detailed_plan.md 5/7): drives the
`ask_clarification` flow (detailed_plan.md 4.5 step 7) turn by turn over the
WebSocket connection in app/routers/chat.py, persisting enough state to
`chat_sessions.langgraph_state` to resume after a disconnect.

This does not use LangGraph's `interrupt()`/checkpointer primitives for the
pause -- that needs an async Postgres checkpointer package not otherwise used
in this project, and our "graph" is cheap enough (a handful of candidates, one
clarification round at a time) to just re-run meta_filter/rag_search/
graph_reasoning/llm_judge each turn. `langgraph_state` is a plain JSON
snapshot of *our own* control state (query params, collected facts, the
pending questions, round count) -- not LangGraph's internal checkpoint format.

Scope decision: clarifying questions are only asked about one "focus" policy at
a time -- the top RAG-ranked candidate by default, or a specific policy the
user picked from a dashboard recommendation card (`target_policy_id` on
`create_session`, see `_resolve_focus_candidate`). All of that policy's
still-unresolved criteria for the current round are sent together as one
`question_batch` rather than trickled out one question per round-trip --
`judge_policy` already judges every criterion for a candidate in a single LLM
call, so there is nothing to gain from asking them one at a time, and batching
means the whole round is answered locally before the next network round-trip.
Untargeted (general chat entry point), this is capped at `_MAX_ROUNDS`: asking
about every candidate's every unclear criterion would make for an exhausting
chat when the user hasn't said which policy they actually care about. But once
a specific policy is targeted, the round cap does not apply -- the whole point
of that flow is to resolve as many of *that* policy's demographics-unresolvable
("정보부족") criteria as possible via yes/no buttons, and the loop already
terminates on its own once every criterion has been asked once (tracked in
`asked_criteria`, so it can never repeat or run away). Once no more questions
are needed (or the untargeted cap is hit), all candidates are re-judged with
whatever facts were collected and scored, so answers about the focus policy
also refine every other candidate's score.

Every in-place mutation of `session.langgraph_state` (a plain dict, not
wrapped in `sqlalchemy.ext.mutable.MutableDict`) must be followed by
`flag_modified(session, "langgraph_state")` before commit -- confirmed by
testing that without it, SQLAlchemy sees `session.langgraph_state = state`
where `state is session.langgraph_state` already and treats it as a no-op, so
the mutated dict (new pending_questions, an appended fact) silently never
reaches Postgres.

Answers are *not* kept in `langgraph_state` (session/policy-scoped) -- an
answer describes the company, not whichever policy happened to trigger the
question, so it's persisted company-wide via app/services/company_facts.py and
matched against each policy's criteria by embedding similarity. This means an
answer given while chatting about one policy also resolves an equivalent
criterion on a different policy in a later session, instead of asking the same
thing again.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.chat import ChatMessage, ChatSession
from app.models.match_result import MatchResult
from app.models.policy import Policy
from app.services.company_facts import (
    FactIndex,
    confirmed_negative_criteria,
    load_fact_index,
    relevant_facts_for,
    save_fact,
    unresolved_criteria,
)
from app.services.company_profile import CompanyDemographics, get_company_demographics
from app.services.graph_reasoning import PolicyGraphEvidence, fetch_graph_evidence
from app.services.llm_judge import criterion_statements, judge_policy
from app.services.match_results import list_match_results, save_match_results
from app.services.matching import PolicyCandidate, meta_filter_policy_ids, rag_search_candidates
from app.services.score_aggregate import MatchReason, ScoredMatch, aggregate_score

_MAX_ROUNDS = 3
_YES_NO_OPTIONS = [{"label": "예", "value": "yes"}, {"label": "아니오", "value": "no"}]


def get_session(db: Session, session_id: str) -> ChatSession | None:
    return db.get(ChatSession, session_id)


def create_session(
    db: Session,
    session_id: str,
    company_id: str,
    query_text: str | None,
    limit: int,
    only_open: bool,
    target_policy_id: str | None = None,
) -> ChatSession:
    company = get_company_demographics(db, company_id)
    default_query = query_text or (
        f"기업규모: {company.company_size}, 지역: {company.region}, "
        f"업종코드: {company.industry_code}, 사업계획: {company.raw_business_plan.get('summary', '')}"
    )
    state = {
        "query_text": default_query,
        "limit": limit,
        "only_open": only_open,
        # Set when the chat is entered from a specific recommendation card
        # (detailed_plan.md 12.2 dashboard "이 정책 재확인" flow) rather than
        # the general chat entry point -- see advance_session's focus_candidate.
        "target_policy_id": target_policy_id,
        "asked_criteria": [],
        "pending_questions": [],
        "rounds": 0,
        "status": "collecting",
    }
    now = datetime.now(timezone.utc)
    session = db.get(ChatSession, session_id)
    if session is None:
        session = ChatSession(
            session_id=session_id, company_id=company_id, langgraph_state=state, updated_at=now
        )
        db.add(session)
    else:
        session.company_id = company_id
        session.langgraph_state = state
        session.updated_at = now
    db.commit()
    return session


def record_answers(db: Session, session: ChatSession, answers: list[dict]) -> None:
    """Records a whole batch of answers at once (all questions from the most
    recent advance_session call are answered together, not one round-trip per
    question -- see advance_session's pending_questions).
    """
    state = session.langgraph_state
    pending_by_id = {q["question_id"]: q for q in state.get("pending_questions", [])}
    for item in answers:
        pending = pending_by_id.get(item.get("question_id"))
        if pending is None:
            continue
        answer_label = "예" if item.get("value") == "yes" else "아니오"
        save_fact(db, session.company_id, pending["criterion_text"], answer_label, pending["policy_id"])
        state["asked_criteria"].append(f"{pending['policy_id']}::{pending['criterion_text']}")
        _log_message(db, session.session_id, "user", answer_label, options=None)

    state["pending_questions"] = []
    state["rounds"] += 1
    session.langgraph_state = state
    flag_modified(session, "langgraph_state")
    session.updated_at = datetime.now(timezone.utc)
    db.commit()


def _serialize_pending_questions(pending_questions: list[dict]) -> list[dict]:
    return [
        {"question_id": q["question_id"], "text": q["text"], "options": _YES_NO_OPTIONS} for q in pending_questions
    ]


def resume_payload(db: Session, session: ChatSession) -> dict | None:
    state = session.langgraph_state
    pending_questions = state.get("pending_questions") or []
    if state["status"] == "collecting" and pending_questions:
        return {"type": "question_batch", "questions": _serialize_pending_questions(pending_questions)}
    if state["status"] == "completed":
        return {"type": "result", "matches": _serialize_cached(db, session.company_id)}
    return None


def _resolve_focus_candidate(
    db: Session, state: dict, candidates: list[PolicyCandidate]
) -> tuple[list[PolicyCandidate], PolicyCandidate | None]:
    """Picks which candidate to ask clarification questions about. If the chat
    was entered from a specific recommendation card (state["target_policy_id"]),
    that policy is used regardless of RAG rank -- otherwise a policy the user
    actually cares about may never get asked about because it wasn't the #1
    match for the generic query text. Falls back to the RAG top rank otherwise.
    """
    target_policy_id = state.get("target_policy_id")
    if not target_policy_id:
        return candidates, candidates[0] if candidates else None

    focus_candidate = next((c for c in candidates if c.policy_id == target_policy_id), None)
    if focus_candidate is None:
        focused = rag_search_candidates(db, [target_policy_id], state["query_text"], limit=1)
        focus_candidate = focused[0] if focused else None
        if focus_candidate is not None:
            candidates = [focus_candidate, *candidates]
    return candidates, focus_candidate


def _judge_with_company_facts(
    company: CompanyDemographics,
    candidate: PolicyCandidate,
    evidence: PolicyGraphEvidence | None,
    fact_index: FactIndex | None,
) -> list:
    if evidence is None:
        return judge_policy(company, candidate, evidence)
    extra_facts = relevant_facts_for(fact_index, criterion_statements(evidence))
    return judge_policy(company, candidate, evidence, extra_facts=extra_facts)


# 정보부족 (no evidence either way) obviously needs a question. 미충족 (LLM judged
# it as not met) is also asked -- that judgment came from RAG evidence/graph
# criteria without the user confirming it, so it can be a false negative; a
# direct yes/no from the user is more reliable than trusting the inference.
# 충족 is not re-asked -- there's nothing to correct in the company's favor.
_NEEDS_CONFIRMATION = {"정보부족", "미충족"}


def _cached_pending_questions(
    db: Session, session: ChatSession, focus_policy_id: str, fact_index: FactIndex | None
) -> list[dict] | None:
    """On a targeted chat's first round, the dashboard/last recalculation
    already judged this exact policy -- that score is why the user clicked
    into chat about it. Reuse those cached reasons as this round's question
    batch instead of spending an OpenAI call re-deriving the same judgments.
    Each candidate criterion is still cross-checked against company_facts
    locally (embedding similarity, no LLM call) in case a fact was recorded
    since the cache was computed, so nothing already-answered gets re-asked.
    Returns None (caller falls back to a live judge_policy call) if there's no
    cached result for this policy yet.
    """
    cached = db.execute(
        select(MatchResult).where(MatchResult.company_id == session.company_id, MatchResult.policy_id == focus_policy_id)
    ).scalar_one_or_none()
    if cached is None:
        return None

    state = session.langgraph_state
    candidate_criteria = [
        reason["criterion"]
        for reason in cached.reasons
        if reason["status"] in _NEEDS_CONFIRMATION
        and f"{focus_policy_id}::{reason['criterion']}" not in state["asked_criteria"]
    ]
    if not candidate_criteria:
        return None

    still_open = unresolved_criteria(fact_index, candidate_criteria)
    return [
        {
            "question_id": f"q{index + 1}",
            "policy_id": focus_policy_id,
            "criterion_text": criterion,
            "text": f"다음 사항에 해당하십니까?\n\n{criterion}",
        }
        for index, criterion in enumerate(still_open)
    ]


def _build_pending_questions(
    db: Session,
    session: ChatSession,
    company: CompanyDemographics,
    focus_candidate: PolicyCandidate,
    graph_evidence: dict[str, PolicyGraphEvidence],
    fact_index: FactIndex | None,
) -> list[dict]:
    state = session.langgraph_state
    if state["rounds"] == 0:
        cached = _cached_pending_questions(db, session, focus_candidate.policy_id, fact_index)
        if cached is not None:
            return cached

    evidence = graph_evidence.get(focus_candidate.policy_id)
    if evidence is None:
        return []
    judgments = _judge_with_company_facts(company, focus_candidate, evidence, fact_index)
    return [
        {
            "question_id": f"q{index + 1}",
            "policy_id": focus_candidate.policy_id,
            "criterion_text": judgment.criterion,
            "text": f"다음 사항에 해당하십니까?\n\n{judgment.criterion}",
        }
        for index, judgment in enumerate(
            j
            for j in judgments
            if j.status in _NEEDS_CONFIRMATION
            and f"{focus_candidate.policy_id}::{j.criterion}" not in state["asked_criteria"]
        )
    ]


def _score_candidates(
    db: Session,
    session: ChatSession,
    company: CompanyDemographics,
    candidates: list[PolicyCandidate],
    focus_candidate: PolicyCandidate | None,
    graph_evidence: dict[str, PolicyGraphEvidence],
    fact_index: FactIndex | None,
) -> list[ScoredMatch]:
    """Re-judges only candidates that could plausibly have changed. A
    candidate whose cached score already has every criterion resolved (no
    정보부족/미충족 left) cannot change from anything just answered -- 충족 is
    final, and there's no unresolved item for a new fact to affect -- so
    re-judging it would spend an OpenAI call to reproduce the same result.
    Only the focus candidate (this round's answers are about it) and
    candidates with something still open are re-judged; everything else
    reuses its cached score/reasons.
    """
    if not candidates:
        return []

    cached_by_policy = {
        result.policy_id: result
        for result in db.execute(
            select(MatchResult).where(
                MatchResult.company_id == session.company_id,
                MatchResult.policy_id.in_([c.policy_id for c in candidates]),
            )
        ).scalars()
    }

    def _needs_rejudge(candidate: PolicyCandidate) -> bool:
        if focus_candidate is not None and candidate.policy_id == focus_candidate.policy_id:
            return True
        cached = cached_by_policy.get(candidate.policy_id)
        if cached is None:
            return True
        return any(reason["status"] in _NEEDS_CONFIRMATION for reason in cached.reasons)

    to_rejudge = [c for c in candidates if _needs_rejudge(c)]
    # Same rationale as orchestrator.py::_llm_judge -- one OpenAI call per
    # candidate, independent and I/O-bound, so run them concurrently.
    fresh_by_policy: dict[str, ScoredMatch] = {}
    if to_rejudge:
        with ThreadPoolExecutor(max_workers=len(to_rejudge)) as executor:
            futures = [
                (
                    candidate,
                    executor.submit(
                        _judge_with_company_facts,
                        company,
                        candidate,
                        graph_evidence.get(candidate.policy_id),
                        fact_index,
                    ),
                )
                for candidate in to_rejudge
            ]
            fresh_by_policy = {
                candidate.policy_id: aggregate_score(candidate.policy_id, candidate.title, future.result())
                for candidate, future in futures
            }

    scored = []
    for candidate in candidates:
        if candidate.policy_id in fresh_by_policy:
            scored.append(fresh_by_policy[candidate.policy_id])
        else:
            cached = cached_by_policy[candidate.policy_id]
            scored.append(
                ScoredMatch(
                    policy_id=candidate.policy_id,
                    title=candidate.title,
                    score=cached.score,
                    reasons=[MatchReason(**reason) for reason in cached.reasons],
                )
            )

    # Mark which 미충족 judgments the user directly confirmed (answered "아니오"
    # to a chat question) rather than the LLM merely inferring it from RAG
    # evidence -- frontend shows these with a distinct label/color.
    negative_criteria = [reason.criterion for match in scored for reason in match.reasons if reason.status == "미충족"]
    confirmed = confirmed_negative_criteria(fact_index, negative_criteria)
    for match in scored:
        for reason in match.reasons:
            if reason.status == "미충족" and reason.criterion in confirmed:
                reason.confirmed = True

    return scored


def advance_session(db: Session, session: ChatSession) -> dict:
    state = session.langgraph_state
    company = get_company_demographics(db, session.company_id)
    eligible_ids = meta_filter_policy_ids(db, state["only_open"])
    candidates = rag_search_candidates(db, eligible_ids, state["query_text"], state["limit"])
    candidates, focus_candidate = _resolve_focus_candidate(db, state, candidates)

    graph_evidence = fetch_graph_evidence([c.policy_id for c in candidates]) if candidates else {}
    fact_index = load_fact_index(db, session.company_id)
    # Untargeted (general chat, no specific recommendation card clicked), cap
    # rounds to avoid an exhausting chat about a candidate the user never
    # asked about. Targeted (detailed_plan.md 12.2 dashboard flow), ask about
    # every one of that policy's 정보부족/미충족 criteria -- the loop below
    # already terminates on its own once none remain (tracked in
    # asked_criteria). All still-unresolved criteria are sent as one batch
    # (not one round-trip per question) -- judge_policy already judges every
    # criterion for this candidate in a single LLM call, so there is no reason
    # to trickle them out one at a time, and the whole point of batching is
    # answering everything locally before the next network round-trip instead
    # of recalculating only after all questions are answered.
    targeted = bool(state.get("target_policy_id"))

    if focus_candidate and (targeted or state["rounds"] < _MAX_ROUNDS):
        pending_questions = _build_pending_questions(
            db, session, company, focus_candidate, graph_evidence, fact_index
        )
        if pending_questions:
            state["pending_questions"] = pending_questions
            session.langgraph_state = state
            flag_modified(session, "langgraph_state")
            session.updated_at = datetime.now(timezone.utc)
            for question in pending_questions:
                _log_message(db, session.session_id, "server", question["text"], options=_YES_NO_OPTIONS)
            db.commit()
            return {"type": "question_batch", "questions": _serialize_pending_questions(pending_questions)}

    scored = _score_candidates(db, session, company, candidates, focus_candidate, graph_evidence, fact_index)
    scored.sort(key=lambda match: match.score, reverse=True)
    save_match_results(db, session.company_id, scored)

    state["status"] = "completed"
    state["pending_questions"] = []
    session.langgraph_state = state
    flag_modified(session, "langgraph_state")
    session.updated_at = datetime.now(timezone.utc)
    _log_message(db, session.session_id, "server", "매칭 결과가 준비되었습니다.", options=None)
    db.commit()

    return {
        "type": "result",
        "matches": [
            {
                "policy_id": match.policy_id,
                "title": match.title,
                "score": match.score,
                "reasons": [asdict(reason) for reason in match.reasons],
            }
            for match in scored
        ],
    }


def _serialize_cached(db: Session, company_id: str) -> list[dict]:
    results = list_match_results(db, company_id)
    titles = {
        policy.policy_id: policy.title
        for policy in db.execute(
            select(Policy).where(Policy.policy_id.in_([r.policy_id for r in results]))
        ).scalars()
    }
    return [
        {
            "policy_id": result.policy_id,
            "title": titles.get(result.policy_id, result.policy_id),
            "score": result.score,
            "reasons": result.reasons,
            "computed_at": result.computed_at.isoformat(),
        }
        for result in results
    ]


def _log_message(db: Session, session_id: str, role: str, content: str, options: list | None) -> None:
    db.add(
        ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            options=options,
            created_at=datetime.now(timezone.utc),
        )
    )
