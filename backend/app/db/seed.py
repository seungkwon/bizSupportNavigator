"""Seeds demo login credentials for the two demo companies (app/services/company_profile.py
has the matching profile rows, seeded separately by seed_demo_profiles) so
`/auth/login` is testable end to end without a signup endpoint (not in
detailed_plan.md 8's API table). Local dev/demo only -- fixed password, not
meant for any real deployment.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.company_auth import CompanyAuth

DEMO_PASSWORD = "demo1234"

_DEMO_ACCOUNTS = (
    ("demo-001", "demo-001@example.com"),
    ("demo-002", "demo-002@example.com"),
)


def seed_demo_accounts(db: Session) -> None:
    for company_id, email in _DEMO_ACCOUNTS:
        if db.get(CompanyAuth, company_id) is not None:
            continue
        db.add(
            CompanyAuth(
                company_id=company_id,
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                created_at=datetime.now(timezone.utc),
            )
        )
    db.commit()
