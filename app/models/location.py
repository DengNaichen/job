import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from sqlalchemy import Column, DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Location(SQLModel, table=True):
    __tablename__: ClassVar[str] = "locations"
    __table_args__ = (Index("ix_locations_canonical_key", "canonical_key", unique=True),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    canonical_key: str = Field()
    display_name: str
    city: str | None = Field(default=None)
    region: str | None = Field(default=None)
    country_code: str | None = Field(default=None)
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    geonames_id: int | None = Field(default=None)
    source_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=text("now()"), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=text("now()"), nullable=False),
    )
