from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate
from app.services.domain.job_location import extract_workplace_type, parse_location_text


class GreenhouseMapper(BaseMapper):
    """Greenhouse data mapper."""

    @property
    def source_name(self) -> str:
        return "greenhouse"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        location_text = self._clean(raw_job.get("location", {}).get("name"))
        raw_employment_type = self._get_employment_type(raw_job)
        employment_type = self._normalize_employment_type(raw_employment_type)
        parsed_loc = parse_location_text(location_text)
        workplace_type = extract_workplace_type([location_text, raw_employment_type])

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("title")),
            apply_url=self._clean(raw_job.get("absolute_url")),
            normalized_apply_url=None,
            status="open",
            location_hints=[
                {
                    "source_raw": location_text,
                    "city": parsed_loc.city,
                    "region": parsed_loc.region,
                    "country_code": parsed_loc.country_code,
                    "workplace_type": workplace_type,
                    "remote_scope": parsed_loc.remote_scope,
                }
            ]
            if (
                location_text
                or parsed_loc.city
                or parsed_loc.region
                or parsed_loc.country_code
            )
            else [],
            department=self._get_first_department_name(raw_job),
            team=None,
            employment_type=employment_type,
            description_html=self._clean(raw_job.get("content")),
            description_plain=None,
            published_at=self._to_datetime_or_none(raw_job.get("first_published")),
            source_updated_at=self._to_datetime_or_none(raw_job.get("updated_at")),
            raw_payload=raw_job,
        )

    @staticmethod
    def _get_first_department_name(raw_job: dict[str, Any]) -> str | None:
        """Get first department name."""
        departments = raw_job.get("departments", [])
        if isinstance(departments, list) and len(departments) > 0:
            return GreenhouseMapper._clean(departments[0].get("name"))
        return None

    @staticmethod
    def _get_employment_type(raw_job: dict[str, Any]) -> str | None:
        """Get employment type from metadata."""
        metadata = raw_job.get("metadata", [])
        if not isinstance(metadata, list):
            return None
        for item in metadata:
            name = item.get("name", "")
            if isinstance(name, str) and "employment" in name.lower():
                return GreenhouseMapper._clean(item.get("value"))
        return None
