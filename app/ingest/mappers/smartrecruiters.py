import html
from datetime import datetime
from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate
from app.services.infra.html_utils import html_to_text


class SmartRecruitersMapper(BaseMapper):
    """SmartRecruiters public postings mapper."""

    SECTION_ORDER = (
        "companyDescription",
        "jobDescription",
        "qualifications",
        "additionalInformation",
    )

    @property
    def source_name(self) -> str:
        return "smartrecruiters"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        description_html = self._build_description_html(raw_job)

        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("name")),
            apply_url=self._clean(raw_job.get("applyUrl"))
            or self._clean(raw_job.get("postingUrl")),
            normalized_apply_url=None,
            status="open",
            location_text=self._clean(self._get_location_text(raw_job)),
            department=self._clean(self._get_label(raw_job, "department")),
            team=self._clean(self._get_label(raw_job, "function")),
            employment_type=self._clean(self._get_label(raw_job, "typeOfEmployment")),
            description_html=description_html,
            description_plain=html_to_text(description_html) if description_html else None,
            published_at=self._to_iso_or_none(raw_job.get("releasedDate")),
            source_updated_at=None,
            raw_payload=raw_job,
        )

    @classmethod
    def _build_description_html(cls, raw_job: dict[str, Any]) -> str | None:
        sections = (raw_job.get("jobAd") or {}).get("sections") or {}
        if not isinstance(sections, dict):
            return None

        parts: list[str] = []
        for key in cls.SECTION_ORDER:
            section = sections.get(key)
            if not isinstance(section, dict):
                continue

            text = section.get("text")
            if not isinstance(text, str) or not text.strip():
                continue

            title = section.get("title")
            title_html = (
                f"<h2>{html.escape(title.strip())}</h2>"
                if isinstance(title, str) and title.strip()
                else None
            )
            parts.append("\n".join(part for part in [title_html, text.strip()] if part))

        return "\n".join(parts) if parts else None

    @staticmethod
    def _clean(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @staticmethod
    def _get_location_text(raw_job: dict[str, Any]) -> str | None:
        location = raw_job.get("location")
        if not isinstance(location, dict):
            return None

        full_location = location.get("fullLocation")
        if isinstance(full_location, str) and full_location.strip():
            return full_location

        parts = []
        for key in ("city", "region", "country"):
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return ", ".join(parts) if parts else None

    @staticmethod
    def _get_label(raw_job: dict[str, Any], key: str) -> str | None:
        value = raw_job.get(key)
        if not isinstance(value, dict):
            return None
        label = value.get("label")
        return label if isinstance(label, str) else None

    @staticmethod
    def _to_iso_or_none(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
