"""Company-facts management endpoints: lets the company view/edit/delete the
facts collected through the chat clarification flow (app/services/chat_service.py,
app/services/company_facts.py) and add new ones directly, instead of only being
able to add facts by answering chat questions. Company-scoped like every other
`/api/companies/*` write (app/core/deps.py::require_company_scope).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_company_scope
from app.db.postgres import get_db
from app.services import company_facts as facts_service

router = APIRouter(prefix="/api/companies", tags=["company-facts"])


class CompanyFactOut(BaseModel):
    id: int
    criterion_text: str
    answer: str
    source_policy_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyFactIn(BaseModel):
    criterion_text: str
    answer: str


@router.get("/{company_id}/facts", response_model=list[CompanyFactOut])
def list_facts(
    company_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> list[CompanyFactOut]:
    return [CompanyFactOut.model_validate(fact) for fact in facts_service.list_facts(db, company_id)]


@router.post("/{company_id}/facts", response_model=CompanyFactOut)
def create_fact(
    company_id: str,
    payload: CompanyFactIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> CompanyFactOut:
    fact = facts_service.create_fact(db, company_id, payload.criterion_text, payload.answer)
    return CompanyFactOut.model_validate(fact)


@router.put("/{company_id}/facts/{fact_id}", response_model=CompanyFactOut)
def update_fact(
    company_id: str,
    fact_id: int,
    payload: CompanyFactIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> CompanyFactOut:
    fact = facts_service.update_fact(db, company_id, fact_id, payload.criterion_text, payload.answer)
    if fact is None:
        raise HTTPException(status_code=404, detail="fact not found")
    return CompanyFactOut.model_validate(fact)


@router.delete("/{company_id}/facts/{fact_id}", status_code=204)
def delete_fact(
    company_id: str,
    fact_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_company_scope),
) -> None:
    if not facts_service.delete_fact(db, company_id, fact_id):
        raise HTTPException(status_code=404, detail="fact not found")
