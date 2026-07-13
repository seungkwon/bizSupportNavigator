"""Company-level fact store (see app/services/company_facts.py for retrieval).

Answers gathered through the chat clarification flow
(app/services/chat_service.py) describe the *company*, not the policy that
happened to trigger the question -- "설립일이 3년 이내이다: 예" is just as true
when judging a different policy later. So these are kept per company_id, not
scoped to a chat session or a single policy, and reused across every policy
judged for that company from then on (including in later, unrelated sessions).
`source_policy_id` is kept only for debugging/audit, not for filtering.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class CompanyFact(Base):
    __tablename__ = "company_facts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    criterion_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(String(16), nullable=False)
    source_policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
