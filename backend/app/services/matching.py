"""Milestone 4 matching: SQL meta-filter + Chroma RAG search, no scoring yet
(detailed_plan.md 4.4/4.5 steps 2-3 `meta_filter` + `rag_search`; `llm_judge` and
`score_aggregate` are Milestone 6). Returns a ranked candidate list only.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.chroma import get_chunk_collection
from app.models.policy import Policy
from app.services.embeddings import get_embedder

_CHUNKS_PER_QUERY_MULTIPLIER = 5
_MAX_CHUNKS_PER_POLICY = 3


@dataclass
class MatchedChunk:
    chunk_id: str
    section_title: str | None
    content: str
    distance: float


@dataclass
class PolicyCandidate:
    policy_id: str
    title: str
    best_distance: float
    matched_chunks: list[MatchedChunk] = field(default_factory=list)


def _eligible_policy_ids(db: Session, only_open: bool) -> list[str]:
    stmt = select(Policy.policy_id)
    if only_open:
        today = date.today()
        stmt = stmt.where((Policy.apply_end_date.is_(None)) | (Policy.apply_end_date >= today))
    return list(db.execute(stmt).scalars())


def search_policy_candidates(
    db: Session,
    query_text: str,
    limit: int = 10,
    only_open: bool = True,
) -> list[PolicyCandidate]:
    """SQL-filters open policies (detailed_plan.md 4.4), then ranks them by the best
    matching chunk's vector similarity to `query_text` (detailed_plan.md 4.5 rag_search).
    """
    eligible_ids = _eligible_policy_ids(db, only_open)
    if not eligible_ids:
        return []

    query_vector = get_embedder().embed_query(query_text)
    result = get_chunk_collection().query(
        query_embeddings=[query_vector],
        n_results=limit * _CHUNKS_PER_QUERY_MULTIPLIER,
        where={"policy_id": {"$in": eligible_ids}},
    )

    ids = result["ids"][0] if result["ids"] else []
    distances = result["distances"][0] if result["distances"] else []
    metadatas = result["metadatas"][0] if result["metadatas"] else []
    documents = result["documents"][0] if result["documents"] else []

    by_policy: dict[str, list[MatchedChunk]] = {}
    order: list[str] = []
    for chunk_id, distance, metadata, content in zip(ids, distances, metadatas, documents):
        policy_id = metadata["policy_id"]
        chunks = by_policy.setdefault(policy_id, [])
        if policy_id not in order:
            order.append(policy_id)
        if len(chunks) < _MAX_CHUNKS_PER_POLICY:
            chunks.append(
                MatchedChunk(
                    chunk_id=chunk_id,
                    section_title=metadata.get("section_title") or None,
                    content=content,
                    distance=distance,
                )
            )

    ranked_policy_ids = order[:limit]
    policies = {
        policy.policy_id: policy
        for policy in db.execute(
            select(Policy).where(Policy.policy_id.in_(ranked_policy_ids))
        ).scalars()
    }

    candidates: list[PolicyCandidate] = []
    for policy_id in ranked_policy_ids:
        policy = policies.get(policy_id)
        if policy is None:
            continue
        matched = by_policy[policy_id]
        candidates.append(
            PolicyCandidate(
                policy_id=policy_id,
                title=policy.title,
                best_distance=min(chunk.distance for chunk in matched),
                matched_chunks=matched,
            )
        )
    return candidates
