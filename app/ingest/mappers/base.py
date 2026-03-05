from abc import ABC, abstractmethod
from datetime import datetime, timezone
import re
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
            - location_hints: Normalized location hints for canonical sync
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

    # Timestamp threshold: values above this are treated as milliseconds
    TIMESTAMP_MS_THRESHOLD = 100_000_000_000

    EMPLOYMENT_TYPE_EXACT_MAP: dict[str, str] = {
        "regular": "full-time",
        "fulltime": "full-time",
        "full time": "full-time",
        "parttime": "part-time",
        "part time": "part-time",
        "contract": "contract",
        "contractor": "contract",
        "per diem": "per-diem",
    }

    EMPLOYMENT_TYPE_CONTAINS_RULES: tuple[tuple[str, str], ...] = (
        ("intern", "intern"),
        ("apprentice", "apprenticeship"),
        ("volunteer", "volunteer"),
        ("third party", "contract"),
        ("contract", "contract"),
        ("fixed term", "temporary"),
        ("temporary", "temporary"),
        ("full time", "full-time"),
        ("part time", "part-time"),
    )

    @staticmethod
    def _clean(value: Any) -> str | None:
        """
        Clean string value.

        Returns stripped string if valid, None otherwise.
        """
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    @classmethod
    def _normalize_employment_type(cls, value: Any) -> str | None:
        """Normalize source employment labels into a small canonical term set."""
        cleaned = cls._clean(value)
        if not cleaned:
            return None

        normalized = cls._normalize_employment_label(cleaned)

        mapped = cls.EMPLOYMENT_TYPE_EXACT_MAP.get(normalized)
        if mapped:
            return mapped

        if "full" in normalized and "part" in normalized:
            return "mixed"

        # Capture phrases like "temp role" in addition to "temporary"/"fixed term".
        if re.search(r"\btemp\b", normalized):
            return "temporary"

        for needle, target in cls.EMPLOYMENT_TYPE_CONTAINS_RULES:
            if needle in normalized:
                return target

        return "other"

    @staticmethod
    def _normalize_employment_label(value: str) -> str:
        """Canonicalize punctuation/casing for employment-type matching."""
        normalized = re.sub(r"[_/-]+", " ", value.lower())
        normalized = re.sub(r"[^a-z0-9\s&+-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @classmethod
    def _to_datetime_or_none(cls, value: Any) -> datetime | None:
        """
        Parse value to datetime, supporting multiple formats.

        Supported formats:
        - ISO 8601 strings (e.g., "2024-01-15T10:30:00Z")
        - Unix timestamps in seconds (e.g., 1705315800)
        - Unix timestamps in milliseconds (e.g., 1705315800000)
        - Numeric strings

        Returns:
            datetime in UTC, or None if parsing fails
        """
        if value in (None, ""):
            return None

        # Handle numeric types (int, float)
        if isinstance(value, (int, float)):
            return cls._parse_timestamp(float(value))

        # Handle strings
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None

            # Try parsing as number first
            try:
                timestamp = float(stripped)
                return cls._parse_timestamp(timestamp)
            except ValueError:
                pass

            # Try parsing as ISO format
            try:
                return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                pass

        return None

    @classmethod
    def _parse_timestamp(cls, timestamp: float) -> datetime | None:
        """Convert Unix timestamp (seconds or milliseconds) to datetime."""
        # Convert milliseconds to seconds if needed
        if timestamp > cls.TIMESTAMP_MS_THRESHOLD:
            timestamp /= 1000.0

        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

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
