"""Auth endpoint (detailed_plan.md 6/8): MVP email/password login only -- there's
no signup endpoint in the plan's API table, so the two demo companies
(app/services/company_profile.py) get seeded accounts at startup (app/db/seed.py)
so login is actually testable end to end.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db.postgres import get_db
from app.models.company_auth import CompanyAuth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    company_id: str


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    account = db.execute(
        select(CompanyAuth).where(CompanyAuth.email == payload.email)
    ).scalar_one_or_none()
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
    token = create_access_token(account.company_id)
    return LoginResponse(access_token=token, company_id=account.company_id)
