"""Milestone 7 chat session orchestration (detailed_plan.md 5/7): drives the
`ask_clarification` flow (detailed_plan.md 4.5 step 7) turn by turn over the
WebSocket connection in app/routers/chat.py, persisting enough state to
`chat_sessions.langgraph_state` to resume after a disconnect.

This does not use LangGraph's `interrupt()`/checkpointer primitives for the
pause -- that needs an async Postgres checkpointer package not otherwise used
in this project, and our "graph" is cheap enough (a handful of candidates, one
clarification round at a time) to just re-run meta_filter/rag_search/
graph_reasoning/llm_judge each turn. `langgraph_state` is a plain JSON
snapshot of *our own* control state (query params, collected facts, the one
pending question, round count) -- not LangGraph's internal checkpoint format.

Scope decision: clarifying questions are only asked about the top RAG-ranked
candidate, one at a time, capped at `_MAX_ROUNDS` total -- asking about every
candidate's every unclear criterion would make for an exhausting chat. Once no
more questions are needed (or the round cap is hit), all candidates are
re-judged with whatever facts were collected and scored.

Every in-place mutation of `session.langgraph_state` (a plain dict, not
wrapped in `sqlalchemy.ext.mutable.MutableDict`) must be followed by
`flag_modified(session, "langgraph_state")` before commit -- confirmed by
testing that without it, SQLAlchemy sees `session.langgraph_state = state`
where `state is session.langgraph_state` already and treats it as a no-op, so
the mutated dict (a new pending_question, an appended fact) silently never
reaches Postgres.
"""

from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.mock.demographics import get_company_demographics
from app.models.chat import ChatMessage, ChatSession
from app.services.graph_reasoning import fetch_graph_evidence
from app.services.llm_judge import judge_policy
from app.services.match_results import list_match_results, save_match_results
from app.services.matching import meta_filter_policy_ids, rag_search_candidates
from app.services.score_aggregate import aggregate_score

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
) -> ChatSession:
    company = get_company_demographics(company_id)
    default_query = query_text or (
        f"기업규모: {company.company_size}, 지역: {company.region}, "
        f"업종코드: {company.industry_code}, 사업계획: {company.raw_business_plan.get('summary', '')}"
    )
    state = {
        "query_text": default_query,
        "limit": limit,
        "only_open": only_open,
        "collected_facts": [],
        "asked_criteria": [],
        "pending_question": None,
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


def record_answer(db: Session, session: ChatSession, question_id: str, value: str) -> None:
    state = session.langgraph_state
    pending = state.get("pending_question")
    if pending is None or pending["question_id"] != question_id:
        return

    answer_label = "예" if value == "yes" else "아니오"
    state["collected_facts"].append(f"{pending['criterion_text']}: {answer_label}")
    state["asked_criteria"].append(f"{pending['policy_id']}::{pending['criterion_text']}")
    state["pending_question"] = None
    state["rounds"] += 1
    session.langgraph_state = state
    flag_modified(session, "langgraph_state")
    session.updated_at = datetime.now(timezone.utc)
    _log_message(db, session.session_id, "user", answer_label, options=None)
    db.commit()


def resume_payload(db: Session, session: ChatSession) -> dict | None:
    state = session.langgraph_state
    pending = state.get("pending_question")
    if state["status"] == "collecting" and pending:
        return {
            "type": "question",
            "question_id": pending["question_id"],
            "text": pending["text"],
            "options": _YES_NO_OPTIONS,
        }
    if state["status"] == "completed":
        return {"type": "result", "matches": _serialize_cached(db, session.company_id)}
    return None


def advance_session(db: Session, session: ChatSession) -> dict:
    state = session.langgraph_state
    company = get_company_demographics(session.company_id)
    eligible_ids = meta_filter_policy_ids(db, state["only_open"])
    candidates = rag_search_candidates(db, eligible_ids, state["query_text"], state["limit"])
    graph_evidence = fetch_graph_evidence([c.policy_id for c in candidates]) if candidates else {}
    extra_facts = state["collected_facts"]

    if candidates and state["rounds"] < _MAX_ROUNDS:
        top = candidates[0]
        evidence = graph_evidence.get(top.policy_id)
        if evidence:
            judgments = judge_policy(company, top, evidence, extra_facts=extra_facts)
            for judgment in judgments:
                key = f"{top.policy_id}::{judgment.criterion}"
                if judgment.status == "정보부족" and key not in state["asked_criteria"]:
                    question_id = f"q{state['rounds'] + 1}"
                    question_text = f"다음 사항에 해당하십니까?\n\n{judgment.criterion}"
                    state["pending_question"] = {
                        "question_id": question_id,
                        "policy_id": top.policy_id,
                        "criterion_text": judgment.criterion,
                        "text": question_text,
                    }
                    session.langgraph_state = state
                    flag_modified(session, "langgraph_state")
                    session.updated_at = datetime.now(timezone.utc)
                    _log_message(db, session.session_id, "server", question_text, options=_YES_NO_OPTIONS)
                    db.commit()
                    return {
                        "type": "question",
                        "question_id": question_id,
                        "text": question_text,
                        "options": _YES_NO_OPTIONS,
                    }

    scored = [
        aggregate_score(
            candidate.policy_id,
            candidate.title,
            judge_policy(company, candidate, graph_evidence.get(candidate.policy_id), extra_facts=extra_facts),
        )
        for candidate in candidates
    ]
    scored.sort(key=lambda match: match.score, reverse=True)
    save_match_results(db, session.company_id, scored)

    state["status"] = "completed"
    state["pending_question"] = None
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
    return [
        {
            "policy_id": result.policy_id,
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
