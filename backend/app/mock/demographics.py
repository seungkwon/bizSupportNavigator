"""Mock adapter for the assumed existing company-demographics service (detailed_plan.md 2.1).

Stands in for `GET /internal/companies/{company_id}/demographics` until the real
service/table is available. Replace with a repository querying PostgreSQL directly
once the upstream system's schema is confirmed.
"""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/internal/companies", tags=["mock-demographics"])


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


_MOCK_COMPANIES: dict[str, CompanyDemographics] = {
    "demo-001": CompanyDemographics(
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
    "demo-002": CompanyDemographics(
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
}


@router.get("/{company_id}/demographics", response_model=CompanyDemographics)
def get_company_demographics(company_id: str) -> CompanyDemographics:
    company = _MOCK_COMPANIES.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return company
