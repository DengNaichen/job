"""
Source service for business logic.

Provides business logic for Source operations including:
- Duplicate name validation
- Reference checking before delete
"""

from datetime import datetime, timezone

from app.models import Source, PlatformType, normalize_name
from app.repositories.job import JobRepository
from app.repositories.source import SourceRepository
from app.repositories.sync_run import SyncRunRepository
from app.schemas.source import SourceCreate, SourceUpdate


class SourceError(Exception):
    """Base exception for Source service errors."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class DuplicateNameError(SourceError):
    """Raised when attempting to create a duplicate name on same platform."""

    def __init__(self, name: str, platform: str):
        super().__init__(
            code="DUPLICATE_NAME",
            message="同一平台下公司名称已存在 (Company name already exists on this platform)",
        )
        self.name = name
        self.platform = platform


class DuplicateIdentifierError(SourceError):
    """Raised when platform+identifier already exists."""

    def __init__(self, platform: str, identifier: str):
        super().__init__(
            code="DUPLICATE_IDENTIFIER",
            message="该平台下标识符已存在 (Identifier already exists on this platform)",
        )
        self.platform = platform
        self.identifier = identifier


class SourceNotFoundError(SourceError):
    """Raised when a source is not found."""

    def __init__(self):
        super().__init__(code="NOT_FOUND", message="数据源不存在")


class HasReferencesError(SourceError):
    """Raised when attempting to delete a source with associated records."""

    def __init__(self):
        super().__init__(
            code="HAS_REFERENCES", message="该数据源有关联的抓取记录，无法删除。建议禁用而非删除"
        )


class HasMutationBlockError(SourceError):
    """Raised when platform or identifier update is blocked by existing job/sync-run references."""

    def __init__(self):
        super().__init__(
            code="HAS_MUTATION_BLOCK",
            message="该数据源有关联的职位或抓取记录，无法修改平台或标识符",
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
        # Normalize the name for uniqueness check
        name_normalized = normalize_name(source_in.name)
        platform = PlatformType(source_in.platform)

        # Check duplicate company name on same platform.
        existing = await self.repository.get_by_name_and_platform(name_normalized, platform)
        if existing:
            raise DuplicateNameError(source_in.name, platform.value)

        # Check duplicate identifier on same platform.
        existing = await self.repository.get_by_platform_and_identifier(
            platform, source_in.identifier
        )
        if existing:
            raise DuplicateIdentifierError(platform.value, source_in.identifier)

        # Create the source entity
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
        source = await self.repository.get_by_id(source_id)
        if not source:
            raise SourceNotFoundError()
        return source

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
        source = await self.repository.get_by_id(source_id)
        if not source:
            raise SourceNotFoundError()

        update_data = source_in.model_dump(exclude_unset=True)
        target_platform = PlatformType(update_data.get("platform", source.platform))

        # Handle name update with duplicate check (within platform)
        if "name" in update_data:
            new_name_normalized = normalize_name(update_data["name"])
            existing = await self.repository.get_by_name_and_platform(
                new_name_normalized, target_platform
            )
            if existing and existing.id != source_id:
                raise DuplicateNameError(update_data["name"], target_platform.value)
            source.name = update_data["name"]
            source.name_normalized = new_name_normalized

        # Handle platform update
        if "platform" in update_data:
            source.platform = target_platform

        # Guard: block structural (platform/identifier) changes when jobs or sync runs reference source
        if "platform" in update_data or "identifier" in update_data:
            if self.job_repository is not None:
                if await self.job_repository.source_id_reference_exists(str(source.id)):
                    raise HasMutationBlockError()
            if self.sync_run_repository is not None:
                if await self.sync_run_repository.has_any_for_source_id(source_id=str(source.id)):
                    raise HasMutationBlockError()

        # Handle identifier update / platform change collision
        if "identifier" in update_data or "platform" in update_data:
            new_identifier = update_data.get("identifier", source.identifier)
            existing = await self.repository.get_by_platform_and_identifier(
                target_platform, new_identifier
            )
            if existing and existing.id != source_id:
                raise DuplicateIdentifierError(target_platform.value, new_identifier)
            source.identifier = new_identifier

        # Handle name collision when only platform changes
        if "platform" in update_data and "name" not in update_data:
            existing = await self.repository.get_by_name_and_platform(
                source.name_normalized, target_platform
            )
            if existing and existing.id != source_id:
                raise DuplicateNameError(source.name, target_platform.value)

        # Handle enabled update
        if "enabled" in update_data:
            source.enabled = update_data["enabled"]

        # Handle notes update
        if "notes" in update_data:
            source.notes = update_data["notes"]

        # Update timestamp
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
        source = await self.repository.get_by_id(source_id)
        if not source:
            raise SourceNotFoundError()

        # Check sync-run references by authoritative source_id.
        if self.sync_run_repository is not None:
            if await self.sync_run_repository.has_any_for_source_id(
                source_id=str(source.id)
            ):
                raise HasReferencesError()

        # Check job references by authoritative source_id.
        if self.job_repository is not None:
            if await self.job_repository.source_id_reference_exists(str(source.id)):
                raise HasReferencesError()

        await self.repository.delete(source)

