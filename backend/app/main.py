from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.migrations import run_additive_migrations
from app.db.postgres import Base, SessionLocal, engine
from app.db.seed import seed_demo_accounts
from app.mock.demographics import router as demographics_router
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.matching import router as matching_router
from app.routers.policies import router as policies_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP stand-in for Alembic migrations; revisit once the schema stabilizes.
    Base.metadata.create_all(bind=engine)
    run_additive_migrations(engine)
    db = SessionLocal()
    try:
        seed_demo_accounts(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(demographics_router)
app.include_router(policies_router)
app.include_router(matching_router)
app.include_router(chat_router)
app.include_router(auth_router)
