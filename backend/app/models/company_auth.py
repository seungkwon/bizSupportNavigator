"""ORM model for company login credentials (detailed_plan.md 6/7 `companies_auth`).

MVP auth only: email/password -> JWT. No SSO/roles (detailed_plan.md 0 defers
those explicitly).
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class CompanyAuth(Base):
    __tablename__ = "companies_auth"

    company_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
