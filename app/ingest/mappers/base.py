from abc import ABC, abstractmethod
from typing import Any

from app.schemas.job import JobCreate
from app.services.domain.country_normalization import normalize_country


class BaseMapper(ABC):
    """
    Base class for data mappers.

    All data source mappers must implement this class to map raw API data
    to standard format.

    Core field mapping rules:
        Required fields:
            - source: Data source identifier (fixed value, e.g., "greenhouse")
            - external_job_id: Job ID from external system
            - title: Job title
            - apply_url: Application URL

        Optional fields:
            - location_text: Work location
            - department: Department
            - employment_type: Employment type (full-time, part-time, contract, etc.)
            - description_html: HTML formatted job description
            - description_plain: Plain text job description
            - published_at: Publication time
            - source_updated_at: Update time in data source

        Raw data:
            - raw_payload: Preserve complete raw API response for future field extraction

    Error handling:
            - Missing fields should return None
            - Empty strings should be converted to None
            - Invalid dates should be converted to None
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Data source name."""
        pass

    @abstractmethod
    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        """
        Map raw data to standard format.

        Args:
            raw_job: Raw job data

        Returns:
            JobCreate in standard format
        """
        pass

    @staticmethod
    def normalize_country_field(raw_value: str | None) -> str | None:
        """Normalize a raw country string from an explicit source-native country field
        to a canonical ISO 3166-1 alpha-2 code.

        Returns the canonical code for high-confidence single-country inputs,
        or None for ambiguous, multi-country, or unrecognized values.
        """
        if not raw_value or not isinstance(raw_value, str) or not raw_value.strip():
            return None
        result = normalize_country(raw_value.strip(), is_explicit_field=True)
        return result.country_code
