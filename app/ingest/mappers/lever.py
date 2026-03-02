from datetime import datetime, timezone
from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate
from app.services.domain.job_location import extract_workplace_type, parse_location_text


class LeverMapper(BaseMapper):
    """Lever postings API mapper."""

    @property
    def source_name(self) -> str:
        return "lever"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        location_text = self._clean(self._get_category(raw_job, "location"))
        commitment = self._clean(self._get_category(raw_job, "commitment"))
        parsed_loc = parse_location_text(location_text)

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("text")),
            apply_url=self._clean(raw_job.get("applyUrl")),
            normalized_apply_url=None,
            status="open",
            location_text=location_text,
            location_city=parsed_loc.city,
            location_region=parsed_loc.region,
            location_country_code=parsed_loc.country_code,
            location_workplace_type=extract_workplace_type([location_text, commitment]),
            department=self._clean(self._get_category(raw_job, "department")),
            team=self._clean(self._get_category(raw_job, "team")),
            employment_type=commitment,
            description_html=self._clean(raw_job.get("description")),
            description_plain=self._clean(raw_job.get("descriptionPlain")),
            published_at=self._to_datetime_or_none(raw_job.get("createdAt")),
            source_updated_at=self._to_datetime_or_none(raw_job.get("updatedAt")),
            raw_payload=raw_job,
        )

    @staticmethod
    def _clean(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def _get_category(raw_job: dict[str, Any], key: str) -> Any:
        categories = raw_job.get("categories")
        if not isinstance(categories, dict):
            return None
        return categories.get(key)

    @staticmethod
    def _to_datetime_or_none(value: Any) -> datetime | None:
        if value in (None, ""):
            return None

        if isinstance(value, (int, float)):
            timestamp = float(value)
        elif isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.isdigit():
                timestamp = float(stripped)
            else:
                try:
                    return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    return None
        else:
            return None

        if timestamp > 100_000_000_000:
            timestamp /= 1000

        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
