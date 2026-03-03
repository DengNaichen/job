"""Source service for business logic."""

from datetime import datetime, timezone

from app.models import PlatformType, Source, normalize_name
from app.repositories.job import JobRepository
from app.repositories.source import SourceRepository
from app.repositories.sync_run import SyncRunRepository
from app.schemas.source import SourceCreate, SourceUpdate
from app.services.application.source_service.errors import (
    DuplicateIdentifierError,
    DuplicateNameError,
    HasMutationBlockError,
    HasReferencesError,
    SourceNotFoundError,
)


class SourceService:
    """Service for Source business logic."""

    def __init__(
        self,
        repository: SourceRepository,
        sync_run_repository: SyncRunRepository | None = None,
        job_repository: JobRepository | None = None,
    ):
        self.repository = repository
        self.sync_run_repository = sync_run_repository
        self.job_repository = job_repository

    async def _get_source_or_raise(self, source_id: str) -> Source:
        """Load source by id or raise SourceNotFoundError."""
        source = await self.repository.get_by_id(source_id)
        if not source:
            raise SourceNotFoundError()
        return source

    async def _raise_if_duplicate_name(
        self,
        *,
        name_normalized: str,
        platform: PlatformType,
        display_name: str,
        source_id: str | None = None,
    ) -> None:
        """Raise DuplicateNameError when name+platform is occupied by another source."""
        existing = await self.repository.get_by_name_and_platform(name_normalized, platform)
        if not existing:
            return
        if source_id is not None and str(existing.id) == source_id:
            return
        raise DuplicateNameError(display_name, platform.value)

    async def _raise_if_duplicate_identifier(
        self,
        *,
        platform: PlatformType,
        identifier: str,
        source_id: str | None = None,
    ) -> None:
        """Raise DuplicateIdentifierError when platform+identifier is occupied by another source."""
        existing = await self.repository.get_by_platform_and_identifier(platform, identifier)
        if not existing:
            return
        if source_id is not None and str(existing.id) == source_id:
            return
        raise DuplicateIdentifierError(platform.value, identifier)

    async def _has_sync_run_references(self, *, source_id: str) -> bool:
        """Return True when sync_run rows reference the source_id."""
        if self.sync_run_repository is None:
            return False
        return await self.sync_run_repository.has_any_for_source_id(source_id=source_id)

    async def _has_job_references(self, *, source_id: str) -> bool:
        """Return True when job rows reference the source_id."""
        if self.job_repository is None:
            return False
        return await self.job_repository.source_id_reference_exists(source_id)

    async def _raise_if_mutation_blocked(self, *, source_id: str) -> None:
        """Raise when structural source mutation is blocked by downstream references."""
        if await self._has_job_references(source_id=source_id):
            raise HasMutationBlockError()
        if await self._has_sync_run_references(source_id=source_id):
            raise HasMutationBlockError()

    async def _raise_if_delete_blocked(self, *, source_id: str) -> None:
        """Raise when source deletion is blocked by downstream references."""
        if await self._has_sync_run_references(source_id=source_id):
            raise HasReferencesError()
        if await self._has_job_references(source_id=source_id):
            raise HasReferencesError()

    async def create_source(self, source_in: SourceCreate) -> Source:
        """
        Create a new source with duplicate name validation.

        Args:
            source_in: Source creation data

        Returns:
            Created Source entity

        Raises:
            DuplicateNameError: If a source with the same normalized name exists on same platform
            DuplicateIdentifierError: If platform + identifier already exists
        """
        name_normalized = normalize_name(source_in.name)
        platform = source_in.platform

        await self._raise_if_duplicate_name(
            name_normalized=name_normalized,
            platform=platform,
            display_name=source_in.name,
        )
        await self._raise_if_duplicate_identifier(
            platform=platform,
            identifier=source_in.identifier,
        )

        source = Source(
            name=source_in.name,
            name_normalized=name_normalized,
            platform=platform,
            identifier=source_in.identifier,
            enabled=source_in.enabled,
            notes=source_in.notes,
        )

        return await self.repository.create(source)

    async def get_source(self, source_id: str) -> Source:
        """
        Get a source by ID.

        Args:
            source_id: Source ID

        Returns:
            Source entity

        Raises:
            SourceNotFoundError: If source not found
        """
        return await self._get_source_or_raise(source_id)

    async def list_sources(
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
            List of sources
        """
        return await self.repository.list(enabled=enabled, platform=platform)

    async def list_slugs(
        self,
        platform: PlatformType = PlatformType.GREENHOUSE,
        enabled: bool = True,
    ) -> list[str]:
        """List source identifiers (slugs) for a platform."""
        sources = await self.repository.list(enabled=enabled, platform=platform)
        return [source.identifier for source in sources]

    async def update_source(self, source_id: str, source_in: SourceUpdate) -> Source:
        """
        Update a source with partial data.

        Args:
            source_id: Source ID
            source_in: Source update data

        Returns:
            Updated Source entity

        Raises:
            SourceNotFoundError: If source not found
            DuplicateNameError: If updating name to an existing name on same platform
            DuplicateIdentifierError: If updating identifier to an existing identifier on same platform
        """
        source = await self._get_source_or_raise(source_id)

        update_data = source_in.model_dump(exclude_unset=True)
        target_platform = PlatformType(update_data.get("platform", source.platform))
        target_identifier = update_data.get("identifier", source.identifier)
        target_name = update_data.get("name", source.name)
        target_name_normalized = normalize_name(target_name)
        source_ref_id = str(source.id)

        if "name" in update_data:
            await self._raise_if_duplicate_name(
                name_normalized=target_name_normalized,
                platform=target_platform,
                display_name=target_name,
                source_id=source_id,
            )

        if "platform" in update_data or "identifier" in update_data:
            await self._raise_if_mutation_blocked(source_id=source_ref_id)

        if "identifier" in update_data or "platform" in update_data:
            await self._raise_if_duplicate_identifier(
                platform=target_platform,
                identifier=target_identifier,
                source_id=source_id,
            )

        if "platform" in update_data and "name" not in update_data:
            await self._raise_if_duplicate_name(
                name_normalized=source.name_normalized,
                platform=target_platform,
                display_name=source.name,
                source_id=source_id,
            )

        if "name" in update_data:
            source.name = target_name
            source.name_normalized = target_name_normalized

        if "platform" in update_data:
            source.platform = target_platform

        if "identifier" in update_data or "platform" in update_data:
            source.identifier = target_identifier

        if "enabled" in update_data:
            source.enabled = update_data["enabled"]

        if "notes" in update_data:
            source.notes = update_data["notes"]

        source.updated_at = datetime.now(timezone.utc)

        return await self.repository.update(source)

    async def delete_source(self, source_id: str) -> None:
        """
        Delete a source (only if no associated records).

        Args:
            source_id: Source ID

        Raises:
            SourceNotFoundError: If source not found
            HasReferencesError: If source has associated SyncRun or Job records
        """
        source = await self._get_source_or_raise(source_id)
        await self._raise_if_delete_blocked(source_id=str(source.id))

        await self.repository.delete(source)
