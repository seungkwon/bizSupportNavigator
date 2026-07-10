from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.models.document_chunk import DocumentChunk
from app.models.policy import Policy
from app.services.document_parser import parse_pending_attachments
from app.services.embedding_pipeline import embed_pending_chunks
from app.services.knowledge_graph import build_pending_graphs
from app.services.policy_collector import sync_policies

router = APIRouter(prefix="/api/policies", tags=["policies"])


class SyncResponse(BaseModel):
    fetched: int
    created: int
    updated: int
    attachments_downloaded: int
    manual_review_count: int
    errors: list[str]


class ParseResponse(BaseModel):
    parsed: int
    failed: int
    chunks_created: int
    errors: list[str]


class EmbedResponse(BaseModel):
    embedded: int
    errors: list[str]


class GraphBuildResponse(BaseModel):
    built: int
    errors: list[str]


class ChunkOut(BaseModel):
    chunk_id: str
    attachment_id: int
    chunk_index: int
    section_title: str | None
    content: str
    page_no: int | None

    model_config = {"from_attributes": True}


class AttachmentOut(BaseModel):
    id: int
    file_name: str
    is_announcement: bool
    needs_manual_review: bool
    downloaded_path: str | None
    format: str | None
    parse_status: str

    model_config = {"from_attributes": True}


class PolicyOut(BaseModel):
    policy_id: str
    title: str
    meta: dict
    apply_start_date: date | None = None
    apply_end_date: date | None = None
    attachments: list[AttachmentOut] = []

    model_config = {"from_attributes": True}


@router.post("/sync", response_model=SyncResponse)
def trigger_sync(
    max_pages: int = Query(default=5, ge=1, le=50),
    page_unit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SyncResponse:
    summary = sync_policies(db, max_pages=max_pages, page_unit=page_unit)
    return SyncResponse(**summary.__dict__)


@router.post("/parse", response_model=ParseResponse)
def trigger_parse(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ParseResponse:
    summary = parse_pending_attachments(db, limit=limit)
    return ParseResponse(**summary.__dict__)


@router.post("/embed", response_model=EmbedResponse)
def trigger_embed(
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> EmbedResponse:
    summary = embed_pending_chunks(db, limit=limit)
    return EmbedResponse(**summary.__dict__)


@router.post("/graph/build", response_model=GraphBuildResponse)
def trigger_graph_build(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> GraphBuildResponse:
    summary = build_pending_graphs(db, limit=limit)
    return GraphBuildResponse(**summary.__dict__)


@router.get("/{policy_id}/chunks", response_model=list[ChunkOut])
def get_policy_chunks(policy_id: str, db: Session = Depends(get_db)) -> list[DocumentChunk]:
    if db.get(Policy, policy_id) is None:
        raise HTTPException(status_code=404, detail="policy not found")
    return list(
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.policy_id == policy_id)
            .order_by(DocumentChunk.attachment_id, DocumentChunk.chunk_index)
        ).scalars()
    )


@router.get("", response_model=list[PolicyOut])
def list_policies(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[Policy]:
    return list(db.execute(select(Policy).limit(limit)).scalars())


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, db: Session = Depends(get_db)) -> Policy:
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="policy not found")
    return policy
