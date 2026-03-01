"""
Source model for data source configuration.

Contains:
- PlatformType enum for supported recruitment platforms
- normalize_name utility for case-insensitive name uniqueness
- Source SQLModel entity for database storage
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, UniqueConstraint
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel


class PlatformType(str, enum.Enum):
    """Recruitment platform types."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    GITHUB = "github"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    EIGHTFOLD = "eightfold"
    APPLE = "apple"
    UBER = "uber"
    TIKTOK = "tiktok"


def normalize_name(name: str) -> str:
    """
    Normalize company name for uniqueness comparison.

    Strips whitespace and converts to lowercase.

    Args:
        name: The company name to normalize

    Returns:
        Normalized name (stripped and lowercased)
    """
    return name.strip().lower()


def build_source_key(platform: PlatformType | str, identifier: str) -> str:
    """Build a stable same-source identity key."""
    identifier_value = identifier.strip()
    if not identifier_value:
        raise ValueError("identifier cannot be empty")

    platform_value = platform.value if isinstance(platform, PlatformType) else str(platform).strip()
    if not platform_value:
        raise ValueError("platform cannot be empty")

    return f"{platform_value}:{identifier_value}"


class Source(SQLModel, table=True):
    """Data source configuration for job scraping."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("name_normalized", "platform", name="uq_sources_name_platform"),
        UniqueConstraint("platform", "identifier", name="uq_sources_platform_identifier"),
    )

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, description="Unique identifier"
    )
    name: str = Field(max_length=255, description="Company name (display name)")
    name_normalized: str = Field(
        max_length=255, index=True, description="Normalized company name for uniqueness check"
    )
    platform: PlatformType = Field(
        sa_column=Column(String(50), nullable=False), description="Platform type"
    )
    identifier: str = Field(max_length=255, description="Platform identifier")
    enabled: bool = Field(default=True, description="Enabled status")
    notes: str | None = Field(default=None, max_length=1000, description="Notes")
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
        description="Created timestamp",
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last updated timestamp",
    )
