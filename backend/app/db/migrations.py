"""Ad-hoc, additive schema patches for columns added after a table already exists.

`Base.metadata.create_all` (app/main.py lifespan) only creates missing tables, it
never alters existing ones -- there's no Alembic in this MVP yet (see main.py).
Each entry here must be an idempotent `ADD COLUMN IF NOT EXISTS` so it's safe to
run on every startup, including against a fresh database that already has the
column via `create_all`.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

_STATEMENTS = (
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ",
)


def run_additive_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for statement in _STATEMENTS:
            conn.execute(text(statement))
