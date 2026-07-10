from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.postgres import Base, engine
from app.mock.demographics import router as demographics_router
from app.routers.health import router as health_router
from app.routers.policies import router as policies_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP stand-in for Alembic migrations; revisit once the schema stabilizes.
    Base.metadata.create_all(bind=engine)
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
