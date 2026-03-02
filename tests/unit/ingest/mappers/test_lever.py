from datetime import datetime, timezone

import pytest

from app.ingest.mappers import LeverMapper


class TestLeverMapper:
    """LeverMapper tests."""

    @pytest.fixture
    def mapper(self):
        return LeverMapper()

    def test_source_name(self, mapper):
        assert mapper.source_name == "lever"

    def test_map_basic_fields(self, mapper):
        raw_job = {
            "id": "job-123",
            "text": "Senior Software Engineer",
            "applyUrl": "https://jobs.lever.co/example/job-123/apply",
            "categories": {
                "location": "San Francisco, CA",
                "department": "Engineering",
                "team": "Platform",
                "commitment": "Full-time",
            },
        }

        result = mapper.map(raw_job)

        assert result.source == "lever"
        assert result.external_job_id == "job-123"
        assert result.title == "Senior Software Engineer"
        assert result.apply_url == "https://jobs.lever.co/example/job-123/apply"
        assert result.location_text == "San Francisco, CA"
        assert result.department == "Engineering"
        assert result.team == "Platform"
        assert result.employment_type == "Full-time"
        assert result.status == "open"

    def test_map_description_and_dates(self, mapper):
        raw_job = {
            "id": "job-1",
            "text": "Engineer",
            "applyUrl": "https://jobs.lever.co/example/job-1/apply",
            "description": "<div>HTML description</div>",
            "descriptionPlain": "Plain description",
            "createdAt": 1720606707905,
            "updatedAt": "1720693107905",
        }

        result = mapper.map(raw_job)

        assert result.description_html == "<div>HTML description</div>"
        assert result.description_plain == "Plain description"
        assert result.published_at == datetime(2024, 7, 10, 10, 18, 27, 905000, tzinfo=timezone.utc)
        assert result.source_updated_at == datetime(
            2024, 7, 11, 10, 18, 27, 905000, tzinfo=timezone.utc
        )

    def test_map_with_invalid_dates(self, mapper):
        raw_job = {
            "id": "job-1",
            "text": "Engineer",
            "applyUrl": "https://jobs.lever.co/example/job-1/apply",
            "createdAt": "not-a-date",
            "updatedAt": {},
        }

        result = mapper.map(raw_job)

        assert result.published_at is None
        assert result.source_updated_at is None

    def test_map_with_missing_optional_fields(self, mapper):
        raw_job = {
            "id": "job-1",
            "text": "Engineer",
            "applyUrl": "https://jobs.lever.co/example/job-1/apply",
        }

        result = mapper.map(raw_job)

        assert result.location_text is None
        assert result.department is None
        assert result.team is None
        assert result.employment_type is None
        assert result.description_html is None
        assert result.description_plain is None
        assert result.published_at is None
        assert result.source_updated_at is None

    def test_map_preserves_raw_payload(self, mapper):
        raw_job = {
            "id": "job-1",
            "text": "Engineer",
            "applyUrl": "https://jobs.lever.co/example/job-1/apply",
            "workplaceType": "hybrid",
            "lists": [{"text": "What you'll do"}],
        }

        result = mapper.map(raw_job)

        assert result.raw_payload == raw_job
        assert result.raw_payload["workplaceType"] == "hybrid"

    def test_map_with_whitespace(self, mapper):
        raw_job = {
            "id": "job-1",
            "text": "  Engineer  ",
            "applyUrl": "  https://jobs.lever.co/example/job-1/apply  ",
            "categories": {
                "location": "  Remote  ",
                "department": "  Engineering  ",
            },
        }

        result = mapper.map(raw_job)

        assert result.title == "Engineer"
        assert result.apply_url == "https://jobs.lever.co/example/job-1/apply"
        assert result.location_text == "Remote"
        assert result.department == "Engineering"
