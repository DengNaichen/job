from datetime import datetime, timezone

import pytest

from app.ingest.mappers import SmartRecruitersMapper


class TestSmartRecruitersMapper:
    """SmartRecruitersMapper tests."""

    @pytest.fixture
    def mapper(self):
        return SmartRecruitersMapper()

    def test_source_name(self, mapper):
        assert mapper.source_name == "smartrecruiters"

    def test_map_basic_fields(self, mapper):
        raw_job = {
            "id": "744000111982085",
            "name": "Director, Visa Pay - APAC",
            "applyUrl": "https://jobs.smartrecruiters.com/Visa/744000111982085-director-visa-pay-apac?oga=true",
            "releasedDate": "2026-02-28T02:43:38.353Z",
            "location": {"fullLocation": "Singapore"},
            "department": {"label": "Product"},
            "function": {"label": "Product Management"},
            "typeOfEmployment": {"label": "Full-time"},
            "jobAd": {
                "sections": {
                    "companyDescription": {
                        "title": "Company Description",
                        "text": "<p>About Visa</p>",
                    },
                    "jobDescription": {
                        "title": "Job Description",
                        "text": "<p>Own the roadmap</p>",
                    },
                }
            },
        }

        result = mapper.map(raw_job)

        assert result.source == "smartrecruiters"
        assert result.external_job_id == "744000111982085"
        assert result.title == "Director, Visa Pay - APAC"
        assert (
            result.apply_url
            == "https://jobs.smartrecruiters.com/Visa/744000111982085-director-visa-pay-apac?oga=true"
        )
        assert result.location_text == "Singapore"
        assert result.department == "Product"
        assert result.team == "Product Management"
        assert result.employment_type == "Full-time"
        assert result.published_at == datetime(2026, 2, 28, 2, 43, 38, 353000, tzinfo=timezone.utc)
        assert result.source_updated_at is None

    def test_map_builds_description_html_and_plain(self, mapper):
        raw_job = {
            "id": "1",
            "name": "Engineer",
            "applyUrl": "https://apply.example/1",
            "jobAd": {
                "sections": {
                    "companyDescription": {
                        "title": "Company Description",
                        "text": "<p>About us</p>",
                    },
                    "jobDescription": {"title": "Job Description", "text": "<p>Build systems</p>"},
                    "qualifications": {"title": "Qualifications", "text": "5+ years<br>Python"},
                    "additionalInformation": {"title": "Additional Information", "text": ""},
                }
            },
        }

        result = mapper.map(raw_job)

        assert "<h2>Company Description</h2>" in result.description_html
        assert "<p>Build systems</p>" in result.description_html
        assert "About us" in result.description_plain
        assert "Build systems" in result.description_plain
        assert "5+ years" in result.description_plain

    def test_map_falls_back_to_posting_url_and_full_location_parts(self, mapper):
        raw_job = {
            "id": "1",
            "name": "Engineer",
            "postingUrl": "https://jobs.smartrecruiters.com/acme/1-engineer",
            "location": {"city": "Montreal", "region": "QC", "country": "Canada"},
            "jobAd": {"sections": {}},
        }

        result = mapper.map(raw_job)

        assert result.apply_url == "https://jobs.smartrecruiters.com/acme/1-engineer"
        assert result.location_text == "Montreal, QC, Canada"
        assert result.description_html is None
        assert result.description_plain is None

    def test_map_with_missing_optional_fields(self, mapper):
        raw_job = {
            "id": "1",
            "name": "Engineer",
            "applyUrl": "https://apply.example/1",
        }

        result = mapper.map(raw_job)

        assert result.location_text is None
        assert result.department is None
        assert result.team is None
        assert result.employment_type is None
        assert result.description_html is None
        assert result.description_plain is None
        assert result.published_at is None

    def test_map_preserves_raw_payload(self, mapper):
        raw_job = {
            "id": "1",
            "name": "Engineer",
            "applyUrl": "https://apply.example/1",
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
        }

        result = mapper.map(raw_job)

        assert result.raw_payload == raw_job
        assert result.raw_payload["uuid"] == "123e4567-e89b-12d3-a456-426614174000"
