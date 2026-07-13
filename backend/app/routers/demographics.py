"""Company demographics endpoints (detailed_plan.md 2.1).

GET stays unauthenticated at the historical `/internal/companies/...` path --
originally modeled as an assumed pre-existing *external* system interface that
this project only reads from (detailed_plan.md 10.5 explicitly keeps it outside
the `require_company_scope` row-level auth applied to `/api/companies/*`). PUT
is new: the company now edits its own profile directly from this app's
frontend (a real user-facing mutation, not a stand-in for another system), so
it requires the bearer JWT to match the path's company_id like every other
company-scoped write.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import require_company_scope
from app.db.postgres import get_db
from app.services.company_profile import (
    CompanyDemographics,
    CompanyDemographicsUpdate,
    get_company_demographics,
    update_company_demographics,
)

router = APIRouter(prefix="/internal/companies", tags=["demographics"])


@router.get("/{company_id}/demographics", response_model=CompanyDemographics)
def get_demographics(company_id: str, db: Session = Depends(get_db)) -> CompanyDemographics:
    try:
        return get_company_demographics(db, company_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="company not found") from exc


@router.put("/{company_id}/demographics", response_model=CompanyDemographics)
def put_demographics(
    company_id: str,
    payload: CompanyDemographicsUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> CompanyDemographics:
    try:
        return update_company_demographics(db, company_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="company not found") from exc
