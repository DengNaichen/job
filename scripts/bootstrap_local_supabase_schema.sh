#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/with_local_supabase_env.sh" "${ROOT_DIR}/.venv/bin/python" - <<'PY'
import asyncio
from sqlalchemy import text
from sqlmodel import SQLModel
import app.models  # noqa: F401
from app.core.database import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)


asyncio.run(main())
PY

"${ROOT_DIR}/scripts/with_local_supabase_env.sh" "${ROOT_DIR}/.venv/bin/alembic" stamp head
