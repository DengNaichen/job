from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate
from app.services.domain.location import extract_workplace_type, parse_location_text


class LeverMapper(BaseMapper):
    """Lever postings API mapper."""

    @property
    def source_name(self) -> str:
        return "lever"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        location_text = self._clean(self._get_category(raw_job, "location"))
        commitment = self._clean(self._get_category(raw_job, "commitment"))
        employment_type = self._normalize_employment_type(commitment)
        parsed_loc = parse_location_text(location_text)
        workplace_type = extract_workplace_type([location_text, commitment])

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("text")),
            apply_url=self._clean(raw_job.get("applyUrl")),
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
            department=self._clean(self._get_category(raw_job, "department")),
            team=self._clean(self._get_category(raw_job, "team")),
            employment_type=employment_type,
            description_html=self._clean(raw_job.get("description")),
            description_plain=self._clean(raw_job.get("descriptionPlain")),
            published_at=self._to_datetime_or_none(raw_job.get("createdAt")),
            source_updated_at=self._to_datetime_or_none(raw_job.get("updatedAt")),
            raw_payload=raw_job,
        )

    @staticmethod
    def _get_category(raw_job: dict[str, Any], key: str) -> Any:
        categories = raw_job.get("categories")
        if not isinstance(categories, dict):
            return None
        return categories.get(key)
