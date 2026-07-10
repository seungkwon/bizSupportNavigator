"""GraphRAG reasoning step (detailed_plan.md 4.5 step 4 `graph_reasoning`).

Surfaces each candidate policy's eligibility/exclusion criteria (and the company
attribute each is tied to, if any) from the Neo4j subgraph built by
app/services/knowledge_graph.py. This does not yet resolve AND/OR relationships
between criteria or judge whether a specific company satisfies them -- that's
`llm_judge`/`score_aggregate` (Milestone 6). Here we only fetch the structured
evidence for those later steps to reason over.
"""

from dataclasses import dataclass, field

from app.db.neo4j import get_neo4j_driver

_QUERY = """
MATCH (p:Policy) WHERE p.policy_id IN $policy_ids
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:REQUIRES]->(e:EligibilityCriterion)
  OPTIONAL MATCH (e)-[:APPLIES_TO]->(ea:CompanyAttribute)
  WITH e, ea WHERE e IS NOT NULL
  RETURN collect({description: e.description, attribute: ea.name}) AS eligibility
}
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:EXCLUDES]->(x:ExclusionCriterion)
  OPTIONAL MATCH (x)-[:APPLIES_TO]->(xa:CompanyAttribute)
  WITH x, xa WHERE x IS NOT NULL
  RETURN collect({description: x.description, attribute: xa.name}) AS exclusion
}
RETURN p.policy_id AS policy_id, eligibility, exclusion
"""


@dataclass
class GraphCriterion:
    description: str
    company_attribute: str | None


@dataclass
class PolicyGraphEvidence:
    policy_id: str
    eligibility_criteria: list[GraphCriterion] = field(default_factory=list)
    exclusion_criteria: list[GraphCriterion] = field(default_factory=list)


def fetch_graph_evidence(policy_ids: list[str]) -> dict[str, PolicyGraphEvidence]:
    if not policy_ids:
        return {}

    with get_neo4j_driver().session() as session:
        records = session.execute_read(
            lambda tx: list(tx.run(_QUERY, policy_ids=policy_ids))
        )

    evidence: dict[str, PolicyGraphEvidence] = {}
    for record in records:
        evidence[record["policy_id"]] = PolicyGraphEvidence(
            policy_id=record["policy_id"],
            eligibility_criteria=[
                GraphCriterion(description=item["description"], company_attribute=item["attribute"])
                for item in record["eligibility"]
            ],
            exclusion_criteria=[
                GraphCriterion(description=item["description"], company_attribute=item["attribute"])
                for item in record["exclusion"]
            ],
        )
    return evidence
