from abc import ABC, abstractmethod
from typing import Any

from app.schemas.job import JobCreate


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
