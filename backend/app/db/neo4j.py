"""Neo4j driver singleton (detailed_plan.md 1.2 GraphRAG store).

Plain `neo4j` driver rather than `langchain-neo4j`: graph writes/reads here are
hand-written Cypher against a fixed schema (Policy/EligibilityCriterion/
ExclusionCriterion/CompanyAttribute, detailed_plan.md 4.3), not a langchain
agent tool, so the extra wrapper doesn't earn its keep -- same call made for
`openai` over `langchain-openai` in announcement_selector.py.
"""

from functools import lru_cache

from neo4j import Driver, GraphDatabase

from app.core.config import get_settings


@lru_cache
def get_neo4j_driver() -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
