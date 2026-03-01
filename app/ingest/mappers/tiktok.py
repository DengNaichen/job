from typing import Any

from app.ingest.mappers.base import BaseMapper
from app.schemas.job import JobCreate


class TikTokMapper(BaseMapper):
    """Mapper for TikTok Careers payloads."""

    @property
    def source_name(self) -> str:
        return "tiktok"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        return JobCreate(
            source=self.source_name,
            external_job_id=str(raw_job.get("id", "")),
            title=self._clean(raw_job.get("title")),
            apply_url=self._build_apply_url(raw_job),
            normalized_apply_url=None,
            status="open",
            location_text=self._location_text(raw_job),
            department=self._nested_label(raw_job.get("job_category")),
            team=self._nested_label(raw_job.get("department_info"))
            or self._nested_label(raw_job.get("job_subject")),
            employment_type=self._nested_label(raw_job.get("recruit_type")),
            description_html=None,
            description_plain=self._description_text(raw_job),
            published_at=None,
            source_updated_at=None,
            raw_payload=raw_job,
        )

    @classmethod
    def _build_apply_url(cls, raw_job: dict[str, Any]) -> str:
        job_id = str(raw_job.get("id", "")).strip()
        if not job_id:
            raise ValueError("TikTok job is missing id")
        return f"https://lifeattiktok.com/search/{job_id}"

    @classmethod
    def _location_text(cls, raw_job: dict[str, Any]) -> str | None:
        city_info = raw_job.get("city_info")
        if not isinstance(city_info, dict):
            return None

        city = cls._nested_label(city_info)
        country = None
        parent = city_info.get("parent")
        if isinstance(parent, dict):
            parent_parent = parent.get("parent")
            if isinstance(parent_parent, dict):
                country = cls._nested_label(parent_parent)

        parts = [part for part in [city, country] if part]
        return ", ".join(parts) if parts else None

    @classmethod
    def _description_text(cls, raw_job: dict[str, Any]) -> str | None:
        parts = []
        for key in ("description", "requirement"):
            cleaned = cls._clean(raw_job.get(key))
            if cleaned:
                parts.append(cleaned)

        job_post_info = raw_job.get("job_post_info")
        if isinstance(job_post_info, dict):
            salary_parts = []
            for label, key in (
                ("Min", "min_salary"),
                ("Max", "max_salary"),
                ("Currency", "currency"),
            ):
                cleaned = cls._clean(job_post_info.get(key))
                if cleaned:
                    salary_parts.append(f"{label}: {cleaned}")
            if salary_parts:
                parts.append("Salary information:\n" + "\n".join(salary_parts))

        return "\n\n".join(parts) if parts else None

    @classmethod
    def _nested_label(cls, value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        for key in ("en_name", "name", "i18n_name"):
            cleaned = cls._clean(value.get(key))
            if cleaned:
                return cleaned
        return None

    @staticmethod
    def _clean(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None
