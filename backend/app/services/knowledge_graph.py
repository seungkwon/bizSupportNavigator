"""GraphRAG knowledge-graph construction (detailed_plan.md 4.3).

Extracts eligibility/exclusion criteria from a policy's parsed chunks via OpenAI
structured output (same `openai` SDK + `response_format=<pydantic model>` pattern
as app/services/announcement_selector.py), then persists a policy-scoped subgraph
to Neo4j:

    (:Policy)-[:REQUIRES]->(:EligibilityCriterion)-[:APPLIES_TO]->(:CompanyAttribute)
    (:Policy)-[:EXCLUDES]->(:ExclusionCriterion)-[:APPLIES_TO]->(:CompanyAttribute)

Criterion nodes are policy-scoped (keyed by policy_id + index); CompanyAttribute
nodes are shared across policies (keyed by name) so graph_reasoning can traverse
by attribute across policies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from neo4j import ManagedTransaction
from openai import OpenAI
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.neo4j import get_neo4j_driver
from app.models.document_chunk import DocumentChunk
from app.models.policy import Policy

_CONTEXT_CHAR_BUDGET = 12000
_PRIORITY_KEYWORDS = ("자격", "대상", "제외", "요건")


class ExtractedCriterion(BaseModel):
    description: str
    company_attribute: str | None = None

    @field_validator("company_attribute")
    @classmethod
    def _blank_or_literal_null_to_none(cls, value: str | None) -> str | None:
        # Structured output sometimes fills the field with the literal text "null"
        # instead of an actual null (confirmed against real bizinfo announcements).
        if value is None or value.strip().lower() in ("", "null", "none"):
            return None
        return value


class GraphExtraction(BaseModel):
    eligibility_criteria: list[ExtractedCriterion]
    exclusion_criteria: list[ExtractedCriterion]


@dataclass
class GraphBuildSummary:
    built: int = 0
    errors: list[str] = field(default_factory=list)


def _gather_policy_text(db: Session, policy_id: str) -> str:
    chunks = list(
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.policy_id == policy_id)
            .order_by(DocumentChunk.attachment_id, DocumentChunk.chunk_index)
        ).scalars()
    )
    prioritized = [
        c for c in chunks if c.section_title and any(k in c.section_title for k in _PRIORITY_KEYWORDS)
    ]
    rest = [c for c in chunks if c not in prioritized]

    parts: list[str] = []
    total = 0
    for chunk in prioritized + rest:
        piece = f"[{chunk.section_title}]\n{chunk.content}" if chunk.section_title else chunk.content
        if parts and total + len(piece) > _CONTEXT_CHAR_BUDGET:
            break
        parts.append(piece)
        total += len(piece)
    return "\n\n".join(parts)


def _extract_criteria(text: str) -> GraphExtraction:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API 키 미설정으로 지식그래프 추출 불가")

    client = OpenAI(api_key=settings.openai_api_key)
    completion = client.beta.chat.completions.parse(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "너는 정부지원사업 공고문에서 신청자격 요건과 제외(신청불가) 요건을 구조화해 "
                    "추출하는 어시스턴트다. 각 요건이 기업의 특정 속성(예: 지역, 업력, 기업규모, "
                    "업종)에 대한 것이면 company_attribute에 그 속성명을 적고, 아니면 null로 둔다."
                ),
            },
            {"role": "user", "content": text},
        ],
        response_format=GraphExtraction,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("LLM 응답 파싱 실패")
    return parsed


def _clear_and_write(
    tx: ManagedTransaction, policy_id: str, title: str, extraction: GraphExtraction
) -> None:
    tx.run(
        "MATCH (p:Policy {policy_id: $policy_id})-[:REQUIRES|EXCLUDES]->(c) DETACH DELETE c",
        policy_id=policy_id,
    )
    tx.run(
        "MERGE (p:Policy {policy_id: $policy_id}) SET p.title = $title",
        policy_id=policy_id,
        title=title,
    )
    for index, criterion in enumerate(extraction.eligibility_criteria):
        tx.run(
            """
            MATCH (p:Policy {policy_id: $policy_id})
            CREATE (c:EligibilityCriterion {policy_id: $policy_id, index: $index, description: $description})
            CREATE (p)-[:REQUIRES]->(c)
            """,
            policy_id=policy_id,
            index=index,
            description=criterion.description,
        )
        if criterion.company_attribute:
            tx.run(
                """
                MATCH (c:EligibilityCriterion {policy_id: $policy_id, index: $index})
                MERGE (a:CompanyAttribute {name: $attribute})
                MERGE (c)-[:APPLIES_TO]->(a)
                """,
                policy_id=policy_id,
                index=index,
                attribute=criterion.company_attribute,
            )
    for index, criterion in enumerate(extraction.exclusion_criteria):
        tx.run(
            """
            MATCH (p:Policy {policy_id: $policy_id})
            CREATE (c:ExclusionCriterion {policy_id: $policy_id, index: $index, description: $description})
            CREATE (p)-[:EXCLUDES]->(c)
            """,
            policy_id=policy_id,
            index=index,
            description=criterion.description,
        )
        if criterion.company_attribute:
            tx.run(
                """
                MATCH (c:ExclusionCriterion {policy_id: $policy_id, index: $index})
                MERGE (a:CompanyAttribute {name: $attribute})
                MERGE (c)-[:APPLIES_TO]->(a)
                """,
                policy_id=policy_id,
                index=index,
                attribute=criterion.company_attribute,
            )


def build_policy_graph(policy_id: str, title: str, extraction: GraphExtraction) -> None:
    with get_neo4j_driver().session() as session:
        session.execute_write(_clear_and_write, policy_id, title, extraction)


def build_pending_graphs(db: Session, limit: int = 50) -> GraphBuildSummary:
    summary = GraphBuildSummary()
    chunked_policy_ids = select(DocumentChunk.policy_id).distinct().subquery()
    policies = list(
        db.execute(
            select(Policy)
            .where(Policy.graph_built_at.is_(None))
            .where(Policy.policy_id.in_(select(chunked_policy_ids.c.policy_id)))
            .limit(limit)
        ).scalars()
    )

    for policy in policies:
        try:
            text = _gather_policy_text(db, policy.policy_id)
            if not text:
                continue
            extraction = _extract_criteria(text)
            build_policy_graph(policy.policy_id, policy.title, extraction)
            policy.graph_built_at = datetime.now(timezone.utc)
            db.add(policy)
            summary.built += 1
        except Exception as exc:  # noqa: BLE001 - degrade to leaving this policy unbuilt, keep going
            summary.errors.append(f"{policy.policy_id}: {exc}")

    db.commit()
    return summary
