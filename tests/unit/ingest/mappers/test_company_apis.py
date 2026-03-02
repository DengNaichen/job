from datetime import datetime, timezone

import pytest

from app.ingest.mappers import AppleMapper, TikTokMapper, UberMapper


class TestAppleMapper:
    @pytest.fixture
    def mapper(self) -> AppleMapper:
        return AppleMapper()

    def test_map_basic_fields(self, mapper: AppleMapper) -> None:
        raw_job = {
            "positionId": "114438004",
            "postingTitle": "CA-Specialist",
            "transformedPostingTitle": "ca-specialist",
            "locations": [{"name": "Canada"}],
            "description": "Deliver great service.",
            "minimumQualifications": "Flexible schedule.",
            "preferredQualifications": "Customer empathy.",
            "postDateInGMT": "2026-02-28T22:16:02.947+00:00",
        }

        result = mapper.map(raw_job)

        assert result.source == "apple"
        assert result.external_job_id == "114438004"
        assert result.title == "CA-Specialist"
        assert result.apply_url == "https://jobs.apple.com/en-us/details/114438004/ca-specialist"
        assert result.location_text == "Canada"
        assert "Description:" in result.description_plain
        assert "Minimum Qualifications:" in result.description_plain
        assert result.published_at == datetime(2026, 2, 28, 22, 16, 2, 947000, tzinfo=timezone.utc)


class TestUberMapper:
    @pytest.fixture
    def mapper(self) -> UberMapper:
        return UberMapper()

    def test_map_basic_fields(self, mapper: UberMapper) -> None:
        raw_job = {
            "id": 154940,
            "title": "Software Engineer II",
            "description": "Build delivery systems.",
            "department": "Engineering",
            "team": "Delivery",
            "timeType": "Full-Time",
            "creationDate": "2026-02-28T10:30:00Z",
            "updatedDate": "2026-02-28T11:30:00Z",
            "location": {
                "city": "San Francisco",
                "region": "California",
                "countryName": "United States",
                "country": "USA",
            },
        }

        result = mapper.map(raw_job)

        assert result.source == "uber"
        assert result.external_job_id == "154940"
        assert result.title == "Software Engineer II"
        assert result.apply_url == "https://www.uber.com/global/en/careers/list/154940/"
        assert result.location_text == "San Francisco, California, United States"
        assert result.location_city == "San Francisco"
        assert result.location_region == "California"
        assert result.location_country_code == "United States"
        assert result.department == "Engineering"
        assert result.team == "Delivery"
        assert result.employment_type == "Full-Time"
        assert result.description_plain == "Build delivery systems."
        assert result.published_at == datetime(2026, 2, 28, 10, 30, 0, tzinfo=timezone.utc)
        assert result.source_updated_at == datetime(2026, 2, 28, 11, 30, 0, tzinfo=timezone.utc)


class TestTikTokMapper:
    @pytest.fixture
    def mapper(self) -> TikTokMapper:
        return TikTokMapper()

    def test_map_basic_fields(self, mapper: TikTokMapper) -> None:
        raw_job = {
            "id": "7610346089650063621",
            "title": "General Policy Manager",
            "description": "Assess policy risk.",
            "requirement": "7+ years experience.",
            "city_info": {
                "en_name": "Kuala Lumpur",
                "parent": {"parent": {"en_name": "Malaysia"}},
            },
            "job_category": {"en_name": "Operations"},
            "department_info": {"en_name": "Trust & Safety"},
            "recruit_type": {"en_name": "Regular"},
            "job_post_info": {"min_salary": "100000", "max_salary": "150000", "currency": "MYR"},
        }

        result = mapper.map(raw_job)

        assert result.source == "tiktok"
        assert result.external_job_id == "7610346089650063621"
        assert result.title == "General Policy Manager"
        assert result.apply_url == "https://lifeattiktok.com/search/7610346089650063621"
        assert result.location_text == "Kuala Lumpur, Malaysia"
        assert result.location_city == "Kuala Lumpur"
        assert result.location_country_code == "Malaysia"
        assert result.department == "Operations"
        assert result.team == "Trust & Safety"
        assert result.employment_type == "Regular"
        assert "Assess policy risk." in result.description_plain
        assert "7+ years experience." in result.description_plain
        assert "Salary information:" in result.description_plain
