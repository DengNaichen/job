"""
Source repository for database operations.

Provides async CRUD operations for Source entities.
"""

from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlatformType, Source


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _normalize_source_timestamps(source: Source | None) -> Source | None:
    if source is None:
        return None
    source.created_at = _ensure_utc(source.created_at)
    source.updated_at = _ensure_utc(source.updated_at)
    return source


class SourceRepository:
    """Repository for Source entity database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, source: Source) -> Source:
        """Create a new source."""
        now = datetime.now(timezone.utc)
        source.created_at = now
        source.updated_at = now
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return _normalize_source_timestamps(source)

    async def get_by_id(self, source_id: str) -> Source | None:
        """Get a source by ID."""
        return _normalize_source_timestamps(await self.session.get(Source, source_id))

    async def get_by_name_and_platform(
        self,
        name_normalized: str,
        platform: PlatformType,
    ) -> Source | None:
        """
        Get a source by normalized name + platform.

        Normalizes the search term before querying to ensure match.
        """
        normalized = name_normalized.strip().lower()
        statement = select(Source).where(
            Source.name_normalized == normalized,
            Source.platform == platform,
        )
        result = await self.session.exec(statement)
        return _normalize_source_timestamps(result.first())

    async def get_by_platform_and_identifier(
        self,
        platform: PlatformType,
        identifier: str,
    ) -> Source | None:
        """Get a source by platform + identifier."""
        statement = select(Source).where(
            Source.platform == platform,
            Source.identifier == identifier.strip(),
        )
        result = await self.session.exec(statement)
        return _normalize_source_timestamps(result.first())

    async def get_by_source_key(self, source_key: str) -> Source | None:
        """
        Resolve a legacy "platform:identifier" source key to a Source entity.

        Splits on the first ':' to extract platform and identifier.
        Returns None if the key is malformed or no matching source is found.
        """
        if ":" not in source_key:
            return None
        platform_str, identifier = source_key.split(":", 1)
        try:
            platform = PlatformType(platform_str.strip())
        except ValueError:
            return None
        return await self.get_by_platform_and_identifier(platform, identifier)

    async def get_by_name_normalized(self, name_normalized: str) -> Source | None:
        """
        Backward-compatible lookup by normalized name only.

        Returns the first matching row across platforms.
        """
        normalized = name_normalized.strip().lower()
        statement = select(Source).where(Source.name_normalized == normalized)
        result = await self.session.exec(statement)
        return _normalize_source_timestamps(result.first())

    async def update(self, source: Source) -> Source:
        """Update an existing source."""
        source.updated_at = datetime.now(timezone.utc)
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return _normalize_source_timestamps(source)

    async def delete(self, source: Source) -> None:
        """Delete a source."""
        await self.session.delete(source)
        await self.session.commit()

    async def list(
        self,
        enabled: bool | None = None,
        platform: PlatformType | None = None,
    ) -> list[Source]:
        """
        List sources with optional enabled/platform filters.

        Args:
            enabled: Filter by enabled status. None returns all.
            platform: Filter by platform. None returns all platforms.

        Returns:
            List of sources matching the filter.
        """
        statement = select(Source)
        if enabled is not None:
            statement = statement.where(Source.enabled == enabled)
        if platform is not None:
            statement = statement.where(Source.platform == platform)
        result = await self.session.exec(statement)
        return [
            normalized
            for source in result.all()
            if (normalized := _normalize_source_timestamps(source)) is not None
        ]
