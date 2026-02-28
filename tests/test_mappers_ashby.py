from datetime import datetime, timezone

import pytest

from app.ingest.mappers import AshbyMapper


class TestAshbyMapper:
    """AshbyMapper tests."""

    @pytest.fixture
    def mapper(self):
        return AshbyMapper()

    def test_source_name(self, mapper):
        assert mapper.source_name == "ashby"

    def test_map_basic_fields(self, mapper):
        raw_job = {
            "id": "145ff46b-1441-4773-bcd3-c8c90baa598a",
            "title": "Engineer Who Can Design, Americas",
            "applyUrl": "https://jobs.ashbyhq.com/ashby/job-1/application",
            "location": "Remote - North to South America",
            "department": "Engineering",
            "team": "Americas Engineering",
            "employmentType": "FullTime",
        }

        result = mapper.map(raw_job)

        assert result.source == "ashby"
        assert result.external_job_id == "145ff46b-1441-4773-bcd3-c8c90baa598a"
        assert result.title == "Engineer Who Can Design, Americas"
        assert result.apply_url == "https://jobs.ashbyhq.com/ashby/job-1/application"
        assert result.location_text == "Remote - North to South America"
        assert result.department == "Engineering"
        assert result.team == "Americas Engineering"
        assert result.employment_type == "FullTime"
        assert result.status == "open"

    def test_map_descriptions_and_dates(self, mapper):
        raw_job = {
            "id": "job-1",
            "title": "Engineer",
            "applyUrl": "https://jobs.ashbyhq.com/example/job-1/application",
            "descriptionHtml": "<p>Join our team</p>",
            "descriptionPlain": "Join our team",
            "publishedAt": "2024-01-15T10:30:00Z",
        }

        result = mapper.map(raw_job)

        assert result.description_html == "<p>Join our team</p>"
        assert result.description_plain == "Join our team"
        assert result.published_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert result.source_updated_at is None

    def test_map_with_invalid_date(self, mapper):
        raw_job = {
            "id": "job-1",
            "title": "Engineer",
            "applyUrl": "https://jobs.ashbyhq.com/example/job-1/application",
            "publishedAt": "invalid-date",
        }

        result = mapper.map(raw_job)

        assert result.published_at is None
        assert result.source_updated_at is None

    def test_map_preserves_raw_payload(self, mapper):
        raw_job = {
            "id": "job-1",
            "title": "Engineer",
            "applyUrl": "https://jobs.ashbyhq.com/example/job-1/application",
            "jobUrl": "https://jobs.ashbyhq.com/example/job-1",
            "workplaceType": "Remote",
        }

        result = mapper.map(raw_job)

        assert result.raw_payload == raw_job
        assert result.raw_payload["jobUrl"] == "https://jobs.ashbyhq.com/example/job-1"
        assert result.raw_payload["workplaceType"] == "Remote"

    def test_map_with_missing_optional_fields(self, mapper):
        raw_job = {
            "id": "job-1",
            "title": "Engineer",
            "applyUrl": "https://jobs.ashbyhq.com/example/job-1/application",
        }

        result = mapper.map(raw_job)

        assert result.location_text is None
        assert result.department is None
        assert result.team is None
        assert result.employment_type is None
        assert result.description_html is None
        assert result.description_plain is None

    def test_map_trims_whitespace(self, mapper):
        raw_job = {
            "id": "job-1",
            "title": "  Engineer  ",
            "applyUrl": "  https://jobs.ashbyhq.com/example/job-1/application  ",
            "location": "  Remote  ",
        }

        result = mapper.map(raw_job)

        assert result.title == "Engineer"
        assert result.apply_url == "https://jobs.ashbyhq.com/example/job-1/application"
        assert result.location_text == "Remote"
