from datetime import datetime
from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate


class AshbyMapper(BaseMapper):
    """Ashby public job board mapper."""

    @property
    def source_name(self) -> str:
        return "ashby"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("title")),
            apply_url=self._clean(raw_job.get("applyUrl")),
            normalized_apply_url=None,
            status="open",
            location_text=self._clean(raw_job.get("location")),
            department=self._clean(raw_job.get("department")),
            team=self._clean(raw_job.get("team")),
            employment_type=self._clean(raw_job.get("employmentType")),
            description_html=self._clean(raw_job.get("descriptionHtml")),
            description_plain=self._clean(raw_job.get("descriptionPlain")),
            published_at=self._to_iso_or_none(raw_job.get("publishedAt")),
            source_updated_at=None,
            raw_payload=raw_job,
        )

    @staticmethod
    def _clean(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def _to_iso_or_none(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
