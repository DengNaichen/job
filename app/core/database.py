from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Track whether tables have been created
_tables_created = False


async def init_db() -> None:
    """Initialize database tables."""
    global _tables_created
    if not _tables_created:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        _tables_created = True


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async session, ensuring tables are created first."""
    await init_db()
    async with AsyncSession(engine) as session:
        try:
            yield session
        finally:
            await session.close()
