import html
from datetime import datetime
from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate


class AppleMapper(BaseMapper):
    """Mapper for Apple Jobs payloads."""

    @property
    def source_name(self) -> str:
        return "apple"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        return JobCreate(
            source=self.source_name,
            external_job_id=self._clean(raw_job.get("positionId")) or str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("postingTitle")),
            apply_url=self._build_apply_url(raw_job),
            normalized_apply_url=None,
            status="open",
            location_text=self._location_text(raw_job),
            location_city=self._get_location_part(raw_job, "city"),
            location_region=self._get_location_part(raw_job, "stateProvince"),
            location_country_code=self.normalize_country_field(
                self._get_location_part(raw_job, "countryName")
            ),
            department=self._team_name(raw_job),
            team=None,
            employment_type=None,
            description_html=self._build_description_html(raw_job),
            description_plain=self._build_description_plain(raw_job),
            published_at=self._to_datetime_or_none(raw_job.get("postDateInGMT")),
            source_updated_at=None,
            raw_payload=raw_job,
        )

    @classmethod
    def _build_apply_url(cls, raw_job: dict[str, Any]) -> str:
        position_id = cls._clean(raw_job.get("positionId"))
        slug = cls._clean(raw_job.get("transformedPostingTitle")) or position_id
        if not position_id or not slug:
            raise ValueError("Apple job is missing apply URL components")
        return f"https://jobs.apple.com/en-us/details/{position_id}/{slug}"

    @classmethod
    def _location_text(cls, raw_job: dict[str, Any]) -> str | None:
        locations = raw_job.get("locations")
        if not isinstance(locations, list):
            return None
        for location in locations:
            if not isinstance(location, dict):
                continue
            name = cls._clean(location.get("name"))
            if name:
                return name
            parts = [
                cls._clean(location.get("city")),
                cls._clean(location.get("stateProvince")),
                cls._clean(location.get("countryName")),
            ]
            text = ", ".join(part for part in parts if part)
            if text:
                return text
        return None

    @classmethod
    def _get_location_part(cls, raw_job: dict[str, Any], key: str) -> str | None:
        locations = raw_job.get("locations")
        if not isinstance(locations, list):
            return None
        for location in locations:
            if not isinstance(location, dict):
                continue
            cleaned = cls._clean(location.get(key))
            if cleaned:
                return cleaned
        return None

    @classmethod
    def _team_name(cls, raw_job: dict[str, Any]) -> str | None:
        team = raw_job.get("team")
        if not isinstance(team, dict):
            return None
        return cls._clean(team.get("teamName"))

    @classmethod
    def _build_description_html(cls, raw_job: dict[str, Any]) -> str | None:
        sections = []
        for title, value in (
            ("Summary", raw_job.get("jobSummary")),
            ("Description", raw_job.get("description")),
            ("Minimum Qualifications", raw_job.get("minimumQualifications")),
            ("Preferred Qualifications", raw_job.get("preferredQualifications")),
            ("Pay & Benefits", raw_job.get("payAndBenefits")),
        ):
            cleaned = cls._clean(value)
            if not cleaned:
                continue
            sections.append(
                f"<h2>{html.escape(title)}</h2><p>{html.escape(cleaned).replace(chr(10), '<br/>')}</p>"
            )
        return "\n".join(sections) if sections else None

    @classmethod
    def _build_description_plain(cls, raw_job: dict[str, Any]) -> str | None:
        sections = []
        for title, value in (
            ("Summary", raw_job.get("jobSummary")),
            ("Description", raw_job.get("description")),
            ("Minimum Qualifications", raw_job.get("minimumQualifications")),
            ("Preferred Qualifications", raw_job.get("preferredQualifications")),
            ("Pay & Benefits", raw_job.get("payAndBenefits")),
        ):
            cleaned = cls._clean(value)
            if not cleaned:
                continue
            sections.append(f"{title}:\n{cleaned}")
        return "\n\n".join(sections) if sections else None

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
