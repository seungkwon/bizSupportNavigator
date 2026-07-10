from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env, independent of the process's working directory (backend/ vs repo root).
_REPO_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV, env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "bizSupportNavigator"
    environment: str = "local"

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 9000
    postgres_db: str = "bizsupport"
    postgres_user: str = "bizsupport"
    postgres_password: str = "bizsupport"

    # Chroma (run locally: `chroma run --path ./data/chroma --port 8000`)
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # bizinfo Open API
    bizinfo_api_key: str = ""

    # Local attachment storage (detailed_plan.md 3.1 download_attachment)
    attachment_storage_dir: str = "./data/attachments"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Embedding model
    embedding_model_name: str = "BAAI/bge-m3"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
