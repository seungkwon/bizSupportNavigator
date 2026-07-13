"""Parses downloaded announcement attachments and persists chunks (detailed_plan.md 4.1/4.2).

Handles the exception contracts the plan calls out: `HWPLoader` raises `ValueError`
on an invalid HWP structure, `HWPXLoader` raises `RuntimeError` on a parse failure.
Both (plus unsupported formats, which `AttachmentLoaderFactory` also raises
`ValueError` for) get routed to the manual-review queue via
`policy_attachments.parse_status` instead of failing the whole batch.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.loaders.factory import AttachmentLoaderFactory
from app.models.document_chunk import DocumentChunk
from app.models.policy import PolicyAttachment
from app.services.chunking import split_into_sections

_factory = AttachmentLoaderFactory()
_PENDING_STATUSES = ("pending", "failed")


@dataclass
class ParseSummary:
    parsed: int = 0
    failed: int = 0
    chunks_created: int = 0
    errors: list[str] = field(default_factory=list)


def parse_attachment(db: Session, attachment: PolicyAttachment) -> int:
    """Parses one attachment, replaces its chunks, and updates parse_status.

    Returns the number of chunks created. Raises ValueError/RuntimeError on parse
    failure after marking the attachment "failed" (caller decides how to handle it).
    """
    existing = db.execute(
        select(DocumentChunk).where(DocumentChunk.attachment_id == attachment.id)
    ).scalars()
    for chunk in existing:
        db.delete(chunk)
    db.flush()

    try:
        documents = _factory.load(attachment.downloaded_path, attachment.format)
    except (ValueError, RuntimeError):
        attachment.parse_status = "failed"
        db.add(attachment)
        raise

    candidates = split_into_sections(documents)
    for index, candidate in enumerate(candidates):
        db.add(
            DocumentChunk(
                chunk_id=f"{attachment.id}:{index:04d}",
                policy_id=attachment.policy_id,
                attachment_id=attachment.id,
                chunk_index=index,
                section_title=candidate.section_title,
                content=candidate.content.replace("\x00", ""),
                page_no=candidate.page_no,
            )
        )
    attachment.parse_status = "parsed"
    db.add(attachment)
    db.flush()
    return len(candidates)


def parse_pending_attachments(db: Session, limit: int = 100) -> ParseSummary:
    summary = ParseSummary()
    attachment_ids = list(
        db.execute(
            select(PolicyAttachment.id)
            .where(PolicyAttachment.is_announcement.is_(True))
            .where(PolicyAttachment.downloaded_path.is_not(None))
            .where(PolicyAttachment.parse_status.in_(_PENDING_STATUSES))
            .limit(limit)
        ).scalars()
    )

    for attachment_id in attachment_ids:
        attachment = db.get(PolicyAttachment, attachment_id)
        try:
            count = parse_attachment(db, attachment)
            db.commit()
            summary.parsed += 1
            summary.chunks_created += count
        except Exception as exc:  # noqa: BLE001 - degrade to manual review, keep parsing the rest
            db.rollback()
            attachment = db.get(PolicyAttachment, attachment_id)
            attachment.parse_status = "failed"
            db.add(attachment)
            db.commit()
            summary.failed += 1
            summary.errors.append(f"{attachment.policy_id}/{attachment.file_name}: {exc}")

    return summary
