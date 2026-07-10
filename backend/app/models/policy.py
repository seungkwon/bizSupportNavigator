"""ORM models for policies collected from bizinfo.go.kr (detailed_plan.md 3.3)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="bizinfo")
    # Parsed out of meta for SQL-level filtering (detailed_plan.md 4.4); region/company-size
    # aren't exposed as clean fields by the bizinfo API (only free-text trgetNm/hashtags),
    # so those stay in `meta` until a reliable extraction rule is added.
    apply_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    apply_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once this policy's knowledge-graph subgraph has been built in Neo4j
    # (detailed_plan.md 4.3); null means "not built yet, or its chunks changed since".
    graph_built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attachments: Mapped[list["PolicyAttachment"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyAttachment(Base):
    __tablename__ = "policy_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("policies.policy_id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    download_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_announcement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_manual_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    downloaded_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    policy: Mapped["Policy"] = relationship(back_populates="attachments")
