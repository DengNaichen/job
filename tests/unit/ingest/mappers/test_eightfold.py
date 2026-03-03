from datetime import datetime, timezone

import pytest

from app.ingest.mappers import EightfoldMapper
from app.models.job import WorkplaceType


class TestEightfoldMapper:
    """EightfoldMapper tests."""

    @pytest.fixture
    def mapper(self) -> EightfoldMapper:
        return EightfoldMapper()

    def test_source_name(self, mapper: EightfoldMapper) -> None:
        assert mapper.source_name == "eightfold"

    def test_map_basic_fields(self, mapper: EightfoldMapper) -> None:
        raw_job = {
            "id": 12345,
            "name": "Senior Software Engineer",
            "_board_base_url": "https://apply.careers.microsoft.com",
            "positionUrl": "/us/en/job/12345",
            "standardizedLocations": ["Toronto, ON, Canada"],
            "locations": ["Canada"],
            "department": "Engineering",
            "workLocationOption": "Up to 50% work from home",
            "jobDescription": "Build distributed systems.",
            "postedTs": 1709164800,
            "creationTs": 1709251200,
        }

        result = mapper.map(raw_job)

        assert result.model_dump()["source"] == "eightfold"
        assert result.external_job_id == "12345"
        assert result.title == "Senior Software Engineer"
        assert result.apply_url == "https://apply.careers.microsoft.com/us/en/job/12345"
        assert result.model_dump()["location_text"] == "Toronto, ON, Canada"
        assert result.model_dump()["location_city"] == "Toronto"
        assert result.model_dump()["location_region"] == "ON"
        assert result.model_dump()["location_country_code"] == "CA"
        assert result.model_dump()["location_workplace_type"] == WorkplaceType.remote
        assert result.department == "Engineering"
        assert result.team is None
        assert result.employment_type == "Up to 50% work from home"
        assert result.description_html is None
        assert result.description_plain == "Build distributed systems."
        assert result.published_at == datetime.fromtimestamp(1709164800, timezone.utc)
        assert result.source_updated_at == datetime.fromtimestamp(1709251200, timezone.utc)

    def test_map_falls_back_to_locations_when_standardized_missing(
        self, mapper: EightfoldMapper
    ) -> None:
        raw_job = {
            "id": "job-1",
            "name": "Designer",
            "_board_base_url": "https://nvidia.eightfold.ai",
            "positionUrl": "/careers/job/1",
            "locations": ["Santa Clara, CA, United States"],
        }

        result = mapper.map(raw_job)

        assert result.apply_url == "https://nvidia.eightfold.ai/careers/job/1"
        assert result.model_dump()["location_text"] == "Santa Clara, CA, United States"
        assert result.model_dump()["location_country_code"] == "US"
        assert result.description_plain is None
        assert result.published_at is None
        assert result.source_updated_at is None

    def test_map_strips_empty_strings_and_supports_millisecond_timestamps(
        self, mapper: EightfoldMapper
    ) -> None:
        raw_job = {
            "id": "job-2",
            "name": "  ML Engineer  ",
            "_board_base_url": " https://nvidia.eightfold.ai ",
            "positionUrl": " /careers/job/2 ",
            "standardizedLocations": ["   "],
            "locations": ["  Austin, TX, United States  "],
            "department": "   ",
            "workLocationOption": "",
            "jobDescription": "   ",
            "postedTs": 1709164800000,
            "creationTs": 1709251200000,
        }

        result = mapper.map(raw_job)

        assert result.title == "ML Engineer"
        assert result.apply_url == "https://nvidia.eightfold.ai/careers/job/2"
        assert result.model_dump()["location_text"] == "Austin, TX, United States"
        assert result.model_dump()["location_country_code"] == "US"
        assert result.department is None
        assert result.employment_type is None
        assert result.description_plain is None
        assert result.published_at == datetime.fromtimestamp(1709164800, timezone.utc)
        assert result.source_updated_at == datetime.fromtimestamp(1709251200, timezone.utc)

    def test_map_preserves_raw_payload(self, mapper: EightfoldMapper) -> None:
        raw_job = {
            "id": "job-3",
            "name": "Architect",
            "_board_base_url": "https://apply.careers.microsoft.com",
            "positionUrl": "/us/en/job/3",
            "atsJobId": "A-123",
        }

        result = mapper.map(raw_job)

        assert result.raw_payload == raw_job
        assert result.raw_payload["atsJobId"] == "A-123"

    def test_map_single_country_text_infers_canonical_code(self, mapper: EightfoldMapper) -> None:
        """When location text clearly identifies one country, country_code is populated."""
        raw_job = {
            "id": "job-single-country",
            "name": "Engineer",
            "_board_base_url": "https://example.eightfold.ai",
            "positionUrl": "/careers/job/sc",
            "standardizedLocations": ["Berlin, Germany"],
        }

        result = mapper.map(raw_job)

        assert result.model_dump()["location_country_code"] == "DE"
        assert result.model_dump()["location_city"] == "Berlin"

    def test_map_ambiguous_multi_country_returns_null(self, mapper: EightfoldMapper) -> None:
        """When location text does not identify a single country, country_code stays None."""
        raw_job = {
            "id": "job-ambiguous",
            "name": "Engineer",
            "_board_base_url": "https://example.eightfold.ai",
            "positionUrl": "/careers/job/amb",
            "standardizedLocations": ["Remote - EMEA"],
        }

        result = mapper.map(raw_job)

        assert result.model_dump()["location_country_code"] is None
        assert result.model_dump()["location_workplace_type"] == WorkplaceType.remote
