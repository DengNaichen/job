from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlatformType, Source, SyncRun


def _make_source(
    identifier: str,
    platform: PlatformType = PlatformType.GREENHOUSE,
) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=platform,
        identifier=identifier,
    )


@pytest.fixture
def source_factory():
    return _make_source


@pytest.fixture
def init_sync_tables():
    async def _init(test_engine) -> None:  # noqa: ANN001
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    return _init


@pytest.fixture
def list_sync_runs():
    async def _list(test_engine) -> Sequence[SyncRun]:  # noqa: ANN001
        async with AsyncSession(test_engine) as session:
            result = await session.exec(select(SyncRun).order_by(SyncRun.created_at))
            return list(result.all())

    return _list
