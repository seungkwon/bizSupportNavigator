"""Auth dependency (detailed_plan.md 6): extracts `current_company` from the
bearer JWT and enforces it against the `company_id` path param on protected
routes, so one company can't read another's candidates/matches/chat by URL
guessing (row-level scoping, per detailed_plan.md 6's requirement).
"""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_company_id

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_company_id(token: str | None = Depends(_oauth2_scheme)) -> str:
    if token is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    company_id = decode_company_id(token)
    if company_id is None:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다")
    return company_id


def require_company_scope(company_id: str, current_company_id: str = Depends(get_current_company_id)) -> str:
    """Depend on this (not `get_current_company_id` directly) in any route whose
    path already declares a `company_id` param -- FastAPI supplies it from the
    path automatically, and this raises 403 if it doesn't match the token."""
    if company_id != current_company_id:
        raise HTTPException(status_code=403, detail="다른 기업의 데이터에 접근할 수 없습니다")
    return company_id
