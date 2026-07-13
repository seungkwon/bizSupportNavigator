"""Company demographics repository (detailed_plan.md 2.1), backing
app/routers/demographics.py's GET/PUT endpoints and every internal caller that
used to import this straight out of the old app/mock/demographics.py stub
(app/services/chat_service.py, app/routers/matching.py, app/services/llm_judge.py,
app/services/orchestrator.py -- the latter two only for the `CompanyDemographics`
type, not the repository functions).

`CompanyDemographics` stays a plain Pydantic model (not the ORM row) so callers
keep working with the same shape as before this was DB-backed.
"""

from datetime import date, datetime, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile


class CompanyDemographics(BaseModel):
    company_id: str
    company_name: str
    biz_registration_no: str
    region: str
    company_size: str
    industry_code: str
    established_date: date
    employee_count: int
    annual_revenue: float
    raw_business_plan: dict

    model_config = {"from_attributes": True}


class CompanyDemographicsUpdate(BaseModel):
    company_name: str
    biz_registration_no: str
    region: str
    company_size: str
    industry_code: str
    established_date: date
    employee_count: int
    annual_revenue: float
    raw_business_plan: dict


def get_company_demographics(db: Session, company_id: str) -> CompanyDemographics:
    profile = db.get(CompanyProfile, company_id)
    if profile is None:
        raise LookupError(f"no company profile for {company_id!r}")
    return CompanyDemographics.model_validate(profile)


def update_company_demographics(
    db: Session, company_id: str, patch: CompanyDemographicsUpdate
) -> CompanyDemographics:
    profile = db.get(CompanyProfile, company_id)
    if profile is None:
        raise LookupError(f"no company profile for {company_id!r}")
    for field, value in patch.model_dump().items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    return CompanyDemographics.model_validate(profile)


_DEMO_PROFILES = (
    CompanyDemographics(
        company_id="demo-001",
        company_name="주식회사 데모",
        biz_registration_no="123-45-67890",
        region="서울",
        company_size="소상공인",
        industry_code="62010",
        established_date=date(2023, 3, 15),
        employee_count=4,
        annual_revenue=250_000_000,
        raw_business_plan={"summary": "AI 기반 SaaS 서비스 개발"},
    ),
    CompanyDemographics(
        company_id="demo-002",
        company_name="테스트 중소기업",
        biz_registration_no="987-65-43210",
        region="경기",
        company_size="중소기업",
        industry_code="26110",
        established_date=date(2018, 7, 1),
        employee_count=45,
        annual_revenue=8_000_000_000,
        raw_business_plan={"summary": "반도체 부품 제조"},
    ),
)


def seed_demo_profiles(db: Session) -> None:
    """Same two demo companies the old in-memory mock shipped with, now inserted
    as real rows so a fresh database still has a usable demo (app/db/seed.py
    calls this alongside seed_demo_accounts at startup, app/main.py lifespan)."""
    now = datetime.now(timezone.utc)
    for demo in _DEMO_PROFILES:
        if db.get(CompanyProfile, demo.company_id) is not None:
            continue
        db.add(CompanyProfile(**demo.model_dump(), updated_at=now))
    db.commit()
