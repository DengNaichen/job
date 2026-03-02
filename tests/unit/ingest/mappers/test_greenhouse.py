import pytest
from datetime import datetime, timezone

from app.ingest.mappers import GreenhouseMapper


class TestGreenhouseMapper:
    """GreenhouseMapper tests."""

    @pytest.fixture
    def mapper(self):
        return GreenhouseMapper()

    def test_source_name(self, mapper):
        assert mapper.source_name == "greenhouse"

    def test_map_basic_fields(self, mapper):
        """Test basic field mapping."""
        raw_job = {
            "id": 123456,
            "title": "Senior Software Engineer",
            "absolute_url": "https://boards.greenhouse.io/example/jobs/123456",
            "location": {"name": "San Francisco, CA"},
        }

        result = mapper.map(raw_job)

        assert result.source == "greenhouse"
        assert result.external_job_id == "123456"
        assert result.title == "Senior Software Engineer"
        assert result.apply_url == "https://boards.greenhouse.io/example/jobs/123456"
        assert result.location_text == "San Francisco, CA"
        assert result.location_country_code == "US"
        assert result.status == "open"

    def test_map_with_department(self, mapper):
        """Test department field mapping."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "departments": [{"name": "Engineering"}, {"name": "Product"}],
        }

        result = mapper.map(raw_job)

        assert result.department == "Engineering"

    def test_map_with_empty_departments(self, mapper):
        """Test empty department list."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "departments": [],
        }

        result = mapper.map(raw_job)

        assert result.department is None

    def test_map_with_employment_type(self, mapper):
        """Test employment type mapping."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "metadata": [
                {"name": "Employment Type", "value": "Full-time"},
                {"name": "Other", "value": "Something"},
            ],
        }

        result = mapper.map(raw_job)

        assert result.employment_type == "Full-time"

    def test_map_with_description(self, mapper):
        """Test description field mapping."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "content": "<p>This is a job description</p>",
        }

        result = mapper.map(raw_job)

        assert result.description_html == "<p>This is a job description</p>"
        assert result.description_plain is None

    def test_map_with_dates(self, mapper):
        """Test date field mapping."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "first_published": "2024-01-15T10:30:00Z",
            "updated_at": "2024-02-20T14:45:00Z",
        }

        result = mapper.map(raw_job)

        assert result.published_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert result.source_updated_at == datetime(2024, 2, 20, 14, 45, 0, tzinfo=timezone.utc)

    def test_map_with_invalid_date(self, mapper):
        """Test invalid date."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "first_published": "invalid-date",
        }

        result = mapper.map(raw_job)

        assert result.published_at is None

    def test_map_preserves_raw_payload(self, mapper):
        """Test raw payload preservation."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
            "custom_field": "custom_value",
        }

        result = mapper.map(raw_job)

        assert result.raw_payload == raw_job
        assert result.raw_payload["custom_field"] == "custom_value"

    def test_map_with_missing_optional_fields(self, mapper):
        """Test missing optional fields."""
        raw_job = {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/1",
        }

        result = mapper.map(raw_job)

        assert result.external_job_id == "1"
        assert result.title == "Engineer"
        assert result.apply_url == "https://example.com/job/1"
        assert result.location_text is None
        assert result.location_country_code is None
        assert result.department is None

    def test_map_with_whitespace(self, mapper):
        """Test string whitespace trimming."""
        raw_job = {
            "id": 1,
            "title": "  Engineer  ",
            "absolute_url": "  https://example.com/job/1  ",
        }

        result = mapper.map(raw_job)

        assert result.title == "Engineer"
        assert result.apply_url == "https://example.com/job/1"

    def test_map_single_country_text_infers_canonical_code(self, mapper):
        """Location text with a clear single country infers canonical alpha-2."""
        raw_job = {
            "id": 2,
            "title": "PM",
            "absolute_url": "https://example.com/job/2",
            "location": {"name": "London, United Kingdom"},
        }

        result = mapper.map(raw_job)

        assert result.location_country_code == "GB"
        assert result.location_city == "London"

    def test_map_ambiguous_text_returns_null_country(self, mapper):
        """Ambiguous region text does not produce a country code."""
        raw_job = {
            "id": 3,
            "title": "Analyst",
            "absolute_url": "https://example.com/job/3",
            "location": {"name": "EMEA"},
        }

        result = mapper.map(raw_job)

        assert result.location_country_code is None

    def test_map_remote_single_country_scope(self, mapper):
        """Remote with a single-country scope infers canonical code."""
        raw_job = {
            "id": 4,
            "title": "Engineer",
            "absolute_url": "https://example.com/job/4",
            "location": {"name": "Remote - Germany"},
        }

        result = mapper.map(raw_job)

        assert result.location_country_code == "DE"
        from app.models.job import WorkplaceType

        assert result.location_workplace_type == WorkplaceType.remote
