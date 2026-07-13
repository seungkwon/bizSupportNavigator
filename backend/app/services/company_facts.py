"""Cross-policy reuse of chat-collected company facts (app/models/company_fact.py
explains why these are stored per-company rather than per-session/per-policy).

`load_fact_index` fetches a company's stored facts once per `advance_session`
call (app/services/chat_service.py); `relevant_facts_for` then embeds one
policy's criteria with the same bge-m3 model used for RAG
(app/services/embeddings.py) and keeps facts whose best cosine similarity to
any of those criteria clears `_SIMILARITY_THRESHOLD`. A fact recorded while
chatting about one policy ("설립일이 3년 이내이다: 예") should resolve a
differently-worded but semantically equivalent criterion on another policy,
without dumping every unrelated fact a company has ever given into every
`judge_policy` call -- and without re-asking a question whose answer is
already effectively known (the point of this whole change: asking the same
thing twice across sessions is exactly what we're avoiding).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company_fact import CompanyFact
from app.services.embeddings import get_embedder

_SIMILARITY_THRESHOLD = 0.65
# Calibrated against real bge-m3 output (2026-07-13): differently-worded
# criteria about the *same* underlying fact (e.g. "휴업 또는 폐업 중인 경우에
# 해당하지 않음" vs. a paraphrase of it) scored ~0.77 cosine similarity, while
# unrelated same-template exclusion clauses ("~에 해당하지 않음" boilerplate
# shared across many policies) still scored 0.54-0.59 just from surface-form
# similarity. 0.55 (the original guess) let those false positives through; 0.65
# sits well above that noise floor while staying below the true-match score.


@dataclass
class FactIndex:
    facts: list[CompanyFact]
    vectors: np.ndarray  # shape (n_facts, dim), row i = embedding of facts[i].criterion_text


def save_fact(db: Session, company_id: str, criterion_text: str, answer: str, source_policy_id: str | None) -> None:
    db.add(
        CompanyFact(
            company_id=company_id,
            criterion_text=criterion_text,
            answer=answer,
            source_policy_id=source_policy_id,
            created_at=datetime.now(timezone.utc),
        )
    )


def list_facts(db: Session, company_id: str) -> list[CompanyFact]:
    stmt = select(CompanyFact).where(CompanyFact.company_id == company_id).order_by(CompanyFact.created_at.desc())
    return list(db.execute(stmt).scalars())


def create_fact(db: Session, company_id: str, criterion_text: str, answer: str) -> CompanyFact:
    fact = CompanyFact(
        company_id=company_id,
        criterion_text=criterion_text,
        answer=answer,
        source_policy_id=None,  # manually added from the company-facts management screen, not a chat answer
        created_at=datetime.now(timezone.utc),
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def update_fact(db: Session, company_id: str, fact_id: int, criterion_text: str, answer: str) -> CompanyFact | None:
    fact = db.get(CompanyFact, fact_id)
    if fact is None or fact.company_id != company_id:
        return None
    fact.criterion_text = criterion_text
    fact.answer = answer
    db.commit()
    db.refresh(fact)
    return fact


def delete_fact(db: Session, company_id: str, fact_id: int) -> bool:
    fact = db.get(CompanyFact, fact_id)
    if fact is None or fact.company_id != company_id:
        return False
    db.delete(fact)
    db.commit()
    return True


def load_fact_index(db: Session, company_id: str) -> FactIndex | None:
    facts = list(db.execute(select(CompanyFact).where(CompanyFact.company_id == company_id)).scalars())
    if not facts:
        return None
    vectors = np.array(get_embedder().embed_documents([fact.criterion_text for fact in facts]))
    return FactIndex(facts=facts, vectors=vectors)


def relevant_facts_for(index: FactIndex | None, criteria_texts: list[str]) -> list[str]:
    if index is None or not criteria_texts:
        return []

    criteria_vectors = np.array(get_embedder().embed_documents(criteria_texts))
    fact_norms = np.linalg.norm(index.vectors, axis=1, keepdims=True)
    criteria_norms = np.linalg.norm(criteria_vectors, axis=1, keepdims=True)
    similarity = (index.vectors @ criteria_vectors.T) / (fact_norms @ criteria_norms.T)
    best_similarity = similarity.max(axis=1)

    return [
        f"{fact.criterion_text}: {fact.answer}"
        for fact, score in zip(index.facts, best_similarity)
        if score >= _SIMILARITY_THRESHOLD
    ]
