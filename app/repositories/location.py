from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.location import Location


class LocationRepository:
    """Repository for Location entity database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, location_id: str) -> Location | None:
        """Get a location by ID."""
        return await self.session.get(Location, location_id)

    async def get_by_canonical_key(self, canonical_key: str) -> Location | None:
        """Get a location by its deterministic canonical key."""
        statement = select(Location).where(Location.canonical_key == canonical_key)
        result = await self.session.exec(statement)
        return result.first()

    async def upsert(self, location: Location) -> Location:
        """Upsert a location by canonical_key. Returns the existing or new record."""
        existing = await self.get_by_canonical_key(location.canonical_key)
        if existing:
            # For Phase 1, we don't update existing locations to avoid side effects.
            # In future phases, we might refresh coordinates or display names.
            return existing

        self.session.add(location)
        return location
