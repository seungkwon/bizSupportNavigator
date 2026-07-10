"""LangGraph orchestrator wiring the full detailed_plan.md 4.5 pipeline:
meta_filter -> rag_search -> graph_reasoning -> llm_judge -> score_aggregate.
`load_company_profile` (step 1) stays the router's job -- it's a plain
mock-adapter call (app/mock/demographics.py), not something that benefits from
graph state. `ask_clarification` (step 7, conditional on missing information)
is Milestone 7's chat/WebSocket flow; for now, missing information simply
surfaces as a "정보부족" reason (app/services/llm_judge.py) instead of pausing
the graph.

Two compiled graphs are exposed: `run_policy_matching` (meta_filter -> rag_search
-> graph_reasoning only, no LLM judging) backs the lightweight
`/policy-candidates` debug endpoint; `run_full_matching` runs the complete
pipeline and backs `/matches` and `/matches/refresh`.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.mock.demographics import CompanyDemographics
from app.services.graph_reasoning import PolicyGraphEvidence, fetch_graph_evidence
from app.services.llm_judge import CriterionJudgment, judge_policy
from app.services.matching import PolicyCandidate, meta_filter_policy_ids, rag_search_candidates
from app.services.score_aggregate import ScoredMatch, aggregate_score


class CandidateState(TypedDict):
    db: Session
    query_text: str
    limit: int
    only_open: bool
    eligible_policy_ids: list[str]
    candidates: list[PolicyCandidate]
    graph_evidence: dict[str, PolicyGraphEvidence]


def _meta_filter(state: CandidateState) -> dict:
    return {"eligible_policy_ids": meta_filter_policy_ids(state["db"], state["only_open"])}


def _rag_search(state: CandidateState) -> dict:
    candidates = rag_search_candidates(
        state["db"], state["eligible_policy_ids"], state["query_text"], state["limit"]
    )
    return {"candidates": candidates}


def _graph_reasoning(state: CandidateState) -> dict:
    policy_ids = [candidate.policy_id for candidate in state["candidates"]]
    return {"graph_evidence": fetch_graph_evidence(policy_ids)}


def _build_candidate_graph():
    graph = StateGraph(CandidateState)
    graph.add_node("meta_filter", _meta_filter)
    graph.add_node("rag_search", _rag_search)
    graph.add_node("graph_reasoning", _graph_reasoning)
    graph.set_entry_point("meta_filter")
    graph.add_edge("meta_filter", "rag_search")
    graph.add_edge("rag_search", "graph_reasoning")
    graph.add_edge("graph_reasoning", END)
    return graph.compile()


_candidate_graph = _build_candidate_graph()


def run_policy_matching(
    db: Session,
    query_text: str,
    limit: int = 10,
    only_open: bool = True,
) -> tuple[list[PolicyCandidate], dict[str, PolicyGraphEvidence]]:
    result = _candidate_graph.invoke(
        {
            "db": db,
            "query_text": query_text,
            "limit": limit,
            "only_open": only_open,
            "eligible_policy_ids": [],
            "candidates": [],
            "graph_evidence": {},
        }
    )
    return result["candidates"], result["graph_evidence"]


class MatchState(CandidateState):
    company: CompanyDemographics
    judgments_by_policy: dict[str, list[CriterionJudgment]]
    scored_matches: list[ScoredMatch]


def _llm_judge(state: MatchState) -> dict:
    judgments_by_policy = {
        candidate.policy_id: judge_policy(
            state["company"], candidate, state["graph_evidence"].get(candidate.policy_id)
        )
        for candidate in state["candidates"]
    }
    return {"judgments_by_policy": judgments_by_policy}


def _score_aggregate(state: MatchState) -> dict:
    scored = [
        aggregate_score(
            candidate.policy_id, candidate.title, state["judgments_by_policy"].get(candidate.policy_id, [])
        )
        for candidate in state["candidates"]
    ]
    scored.sort(key=lambda match: match.score, reverse=True)
    return {"scored_matches": scored}


def _build_full_graph():
    graph = StateGraph(MatchState)
    graph.add_node("meta_filter", _meta_filter)
    graph.add_node("rag_search", _rag_search)
    graph.add_node("graph_reasoning", _graph_reasoning)
    graph.add_node("llm_judge", _llm_judge)
    graph.add_node("score_aggregate", _score_aggregate)
    graph.set_entry_point("meta_filter")
    graph.add_edge("meta_filter", "rag_search")
    graph.add_edge("rag_search", "graph_reasoning")
    graph.add_edge("graph_reasoning", "llm_judge")
    graph.add_edge("llm_judge", "score_aggregate")
    graph.add_edge("score_aggregate", END)
    return graph.compile()


_full_graph = _build_full_graph()


def run_full_matching(
    db: Session,
    company: CompanyDemographics,
    query_text: str,
    limit: int = 10,
    only_open: bool = True,
) -> list[ScoredMatch]:
    result = _full_graph.invoke(
        {
            "db": db,
            "company": company,
            "query_text": query_text,
            "limit": limit,
            "only_open": only_open,
            "eligible_policy_ids": [],
            "candidates": [],
            "graph_evidence": {},
            "judgments_by_policy": {},
            "scored_matches": [],
        }
    )
    return result["scored_matches"]
