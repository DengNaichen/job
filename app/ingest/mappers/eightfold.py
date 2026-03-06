from typing import Any
from urllib.parse import urljoin

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate
from app.services.domain.location import extract_workplace_type, parse_location_text


class EightfoldMapper(BaseMapper):
    """Mapper for Eightfold raw job payloads."""

    @property
    def source_name(self) -> str:
        return "eightfold"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        location_text = self._pick_location(raw_job)
        work_location_option = self._clean(raw_job.get("workLocationOption"))
        employment_type = self._normalize_employment_type(
            raw_job.get("employmentType") or raw_job.get("workerType") or raw_job.get("typeOfEmployment")
        )
        parsed_loc = parse_location_text(location_text)
        workplace_type = extract_workplace_type([location_text, work_location_option])

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job["id"]),
            title=self._clean(raw_job.get("name")),
            apply_url=self._build_apply_url(raw_job),
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
            department=self._clean(raw_job.get("department")),
            team=None,
            employment_type=employment_type,
            description_html=None,
            description_plain=self._clean(raw_job.get("jobDescription")),
            published_at=self._to_datetime_or_none(raw_job.get("postedTs")),
            source_updated_at=self._to_datetime_or_none(raw_job.get("creationTs")),
            raw_payload=raw_job,
        )

    @classmethod
    def _build_apply_url(cls, raw_job: dict[str, Any]) -> str:
        base_url = cls._clean(raw_job.get("_board_base_url"))
        position_url = cls._clean(raw_job.get("positionUrl"))
        if not base_url or not position_url:
            raise ValueError("Eightfold job is missing apply URL components")
        return urljoin(f"{base_url.rstrip('/')}/", position_url.lstrip("/"))

    @classmethod
    def _pick_location(cls, raw_job: dict[str, Any]) -> str | None:
        for key in ("standardizedLocations", "locations"):
            value = raw_job.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                cleaned = cls._clean(item)
                if cleaned:
                    return cleaned
        return None
