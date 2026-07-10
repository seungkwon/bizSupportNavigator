"""Embeds pending document_chunks and upserts them into Chroma (detailed_plan.md 4.2).

Content/metadata stay the source of truth in Postgres; this only pushes vectors
into Chroma keyed by `chunk_id` and stamps `embedded_at` so re-runs skip work
already done. Re-parsing an attachment (app/services/document_parser.py) deletes
and recreates its chunks, so a re-parsed chunk naturally starts as unembedded again.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.chroma import get_chunk_collection
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import get_embedder

_BATCH_SIZE = 64


@dataclass
class EmbedSummary:
    embedded: int = 0
    errors: list[str] = field(default_factory=list)


def embed_pending_chunks(db: Session, limit: int = 500) -> EmbedSummary:
    summary = EmbedSummary()
    chunks = list(
        db.execute(
            select(DocumentChunk).where(DocumentChunk.embedded_at.is_(None)).limit(limit)
        ).scalars()
    )
    if not chunks:
        return summary

    embedder = get_embedder()
    collection = get_chunk_collection()

    for start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[start : start + _BATCH_SIZE]
        try:
            vectors = embedder.embed_documents([chunk.content for chunk in batch])
            collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                embeddings=vectors,
                documents=[chunk.content for chunk in batch],
                metadatas=[
                    {
                        "policy_id": chunk.policy_id,
                        "attachment_id": chunk.attachment_id,
                        "chunk_index": chunk.chunk_index,
                        "section_title": chunk.section_title or "",
                        "page_no": chunk.page_no if chunk.page_no is not None else -1,
                    }
                    for chunk in batch
                ],
            )
        except Exception as exc:  # noqa: BLE001 - degrade to leaving this batch unembedded, keep going
            summary.errors.append(f"batch@{start}: {exc}")
            continue

        now = datetime.now(timezone.utc)
        for chunk in batch:
            chunk.embedded_at = now
            db.add(chunk)
        summary.embedded += len(batch)

    db.commit()
    return summary
