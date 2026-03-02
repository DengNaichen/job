from datetime import datetime
from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate


class UberMapper(BaseMapper):
    """Mapper for Uber Careers payloads."""

    @property
    def source_name(self) -> str:
        return "uber"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("title")),
            apply_url=self._build_apply_url(raw_job),
            normalized_apply_url=None,
            status="open",
            location_text=self._location_text(raw_job),
            location_city=self._get_location_part(raw_job, "city"),
            location_region=self._get_location_part(raw_job, "region"),
            location_country_code=self.normalize_country_field(
                self._get_location_part(raw_job, "countryName")
                or self._get_location_part(raw_job, "country")
            ),
            department=self._clean(raw_job.get("department")),
            team=self._clean(raw_job.get("team")),
            employment_type=self._clean(raw_job.get("timeType")),
            description_html=None,
            description_plain=self._clean(raw_job.get("description")),
            published_at=self._to_datetime_or_none(raw_job.get("creationDate")),
            source_updated_at=self._to_datetime_or_none(raw_job.get("updatedDate")),
            raw_payload=raw_job,
        )

    @classmethod
    def _build_apply_url(cls, raw_job: dict[str, Any]) -> str:
        job_id = str(raw_job.get("id", "")).strip()
        if not job_id:
            raise ValueError("Uber job is missing id")
        return f"https://www.uber.com/global/en/careers/list/{job_id}/"

    @classmethod
    def _location_text(cls, raw_job: dict[str, Any]) -> str | None:
        for key in ("location", "allLocations"):
            value = raw_job.get(key)
            if isinstance(value, dict):
                text = cls._format_location(value)
                if text:
                    return text
            elif isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    text = cls._format_location(item)
                    if text:
                        return text
        return None

    @classmethod
    def _format_location(cls, location: dict[str, Any]) -> str | None:
        parts = [
            cls._clean(location.get("city")),
            cls._clean(location.get("region")),
            cls._clean(location.get("countryName")) or cls._clean(location.get("country")),
        ]
        normalized: list[str] = []
        for part in parts:
            if part and part not in normalized:
                normalized.append(part)
        return ", ".join(normalized) if normalized else None

    @classmethod
    def _get_location_part(cls, raw_job: dict[str, Any], key: str) -> str | None:
        for loc_key in ("location", "allLocations"):
            value = raw_job.get(loc_key)
            if isinstance(value, dict):
                cleaned = cls._clean(value.get(key))
                if cleaned:
                    return cleaned
            elif isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    cleaned = cls._clean(item.get(key))
                    if cleaned:
                        return cleaned
        return None

    @staticmethod
    def _clean(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def _to_datetime_or_none(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
