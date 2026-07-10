"""LangGraph orchestrator wiring meta_filter -> rag_search -> graph_reasoning
(detailed_plan.md 4.5 steps 2-4). `load_company_profile` (step 1) stays the
router's job -- it's a plain mock-adapter call (app/mock/demographics.py), not
something that benefits from graph state. `llm_judge`/`score_aggregate`/
`ask_clarification` (steps 5-7) are Milestone 6 and will extend this graph.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.services.graph_reasoning import PolicyGraphEvidence, fetch_graph_evidence
from app.services.matching import PolicyCandidate, meta_filter_policy_ids, rag_search_candidates


class MatchState(TypedDict):
    db: Session
    query_text: str
    limit: int
    only_open: bool
    eligible_policy_ids: list[str]
    candidates: list[PolicyCandidate]
    graph_evidence: dict[str, PolicyGraphEvidence]


def _meta_filter(state: MatchState) -> dict:
    return {"eligible_policy_ids": meta_filter_policy_ids(state["db"], state["only_open"])}


def _rag_search(state: MatchState) -> dict:
    candidates = rag_search_candidates(
        state["db"], state["eligible_policy_ids"], state["query_text"], state["limit"]
    )
    return {"candidates": candidates}


def _graph_reasoning(state: MatchState) -> dict:
    policy_ids = [candidate.policy_id for candidate in state["candidates"]]
    return {"graph_evidence": fetch_graph_evidence(policy_ids)}


def _build_graph():
    graph = StateGraph(MatchState)
    graph.add_node("meta_filter", _meta_filter)
    graph.add_node("rag_search", _rag_search)
    graph.add_node("graph_reasoning", _graph_reasoning)
    graph.set_entry_point("meta_filter")
    graph.add_edge("meta_filter", "rag_search")
    graph.add_edge("rag_search", "graph_reasoning")
    graph.add_edge("graph_reasoning", END)
    return graph.compile()


_compiled_graph = _build_graph()


def run_policy_matching(
    db: Session,
    query_text: str,
    limit: int = 10,
    only_open: bool = True,
) -> tuple[list[PolicyCandidate], dict[str, PolicyGraphEvidence]]:
    result = _compiled_graph.invoke(
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
