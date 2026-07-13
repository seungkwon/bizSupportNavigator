"""ORM model backing company demographics (detailed_plan.md 2.1).

Originally an assumed-external, read-only interface stubbed out in
app/mock/demographics.py (a hardcoded in-memory dict). Promoted to a real
table so the company can edit its own profile from the frontend
(app/routers/demographics.py exposes GET + PUT); demo rows are seeded at
startup by app/services/company_profile.py::seed_demo_profiles so a fresh
database still boots into a working demo.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    company_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    biz_registration_no: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    company_size: Mapped[str] = mapped_column(String(64), nullable=False)
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False)
    established_date: Mapped[date] = mapped_column(Date, nullable=False)
    employee_count: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_revenue: Mapped[float] = mapped_column(Float, nullable=False)
    raw_business_plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
