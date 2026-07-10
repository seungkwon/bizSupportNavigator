"""ORM model for parsed/chunked attachment text (detailed_plan.md 7).

`chunk_id` is a stable string so it can double as the Chroma vector-store key once
embedding is wired up (detailed_plan.md 1.2: content/metadata live in Postgres,
vectors in Chroma, cross-referenced by chunk_id).
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("policies.policy_id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("policy_attachments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
