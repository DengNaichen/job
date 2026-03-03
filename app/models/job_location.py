import uuid
from datetime import datetime, timezone
from typing import ClassVar, TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlmodel import Field, SQLModel, Relationship

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.location import Location


class JobLocation(SQLModel, table=True):
    __tablename__: ClassVar[str] = "job_locations"
    __table_args__ = (
        UniqueConstraint("job_id", "location_id", name="uq_job_location_pair"),
        # ix_job_locations_primary_one_per_job is created by the Alembic migration.
        # Do NOT re-declare it here — SQLModel.metadata.create_all (used in tests)
        # would fail on SQLite (syntax error) or conflict in Postgres.
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    job_id: str = Field(
        sa_column=Column(String(36), ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    )
    location_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False
        )
    )
    is_primary: bool = Field(
        default=False, sa_column=Column(Boolean, server_default=text("false"), nullable=False)
    )
    source_raw: str | None = Field(default=None)
    workplace_type: str = Field(
        default="unknown",
        sa_column=Column(String(32), server_default=text("'unknown'"), nullable=False),
    )
    remote_scope: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=text("now()"), nullable=False),
    )

    # Relationships
    job: "Job" = Relationship(back_populates="job_locations")
    location: "Location" = Relationship(back_populates="job_locations")
