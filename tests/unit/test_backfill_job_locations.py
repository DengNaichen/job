import pytest

from app.models.job import Job, WorkplaceType
from scripts.backfill_job_locations import apply_backfill_to_job

def test_apply_backfill_high_confidence():
    """High confidence raw payload should populate fields where they are missing."""
    job = Job(
        source="smartrecruiters",
        raw_payload={
            "name": "Test Job",
            "applyUrl": "http://test",
            "location": {
                "city": "Paris",
                "region": "IDF",
                "country": "FR",
                "remote": True
            }
        },
        location_text="France"
    )
    
    assert apply_backfill_to_job(job) is True
    assert job.location_city == "Paris"
    assert job.location_region == "IDF"
    assert job.location_country_code == "FR"
    assert job.location_workplace_type == WorkplaceType.remote


def test_apply_backfill_low_confidence_fallback():
    """Should fallback to text parsing if raw_payload doesn't yield structure."""
    job = Job(
        source="ashby",
        raw_payload={"title": "Test", "applyUrl": "http://test"},
        location_text="San Francisco, CA"
    )
    
    assert apply_backfill_to_job(job) is True
    assert job.location_city == "San Francisco"
    assert job.location_region == "CA"
    assert job.location_country_code == "US"


def test_apply_backfill_idempotent_reruns():
    """Running twice shouldn't change already backfilled data if it yielded same result."""
    job = Job(
        source="smartrecruiters",
        raw_payload={
            "name": "Test Job",
            "applyUrl": "http://test",
            "location": {
                "city": "Paris",
                "region": "IDF",
                "country": "FR"
            }
        }
    )
    
    assert apply_backfill_to_job(job) is True
    assert job.location_city == "Paris"
    
    # Second run should return False (no change)
    assert apply_backfill_to_job(job) is False


def test_protection_against_low_confidence_overwrites():
    """If existing data is present, low-confidence text parse shouldn't overwrite it."""
    job = Job(
        source="ashby",
        location_city="Existing City",
        location_region="EX",
        location_country_code="US",
        location_text="San Francisco, CA",
        raw_payload={"title": "Test", "applyUrl": "http://test"} # Will trigger ashby mapper which uses parse_location_text (low confidence)
    )
    
    # Text says "San Francisco, CA", but we have "Existing City"
    assert apply_backfill_to_job(job) is False
    assert job.location_city == "Existing City"
    assert job.location_region == "EX"

def test_high_confidence_overwrites():
    """High confidence sources CAN overwrite if they parse better data."""
    job = Job(
        source="smartrecruiters",
        location_city="Old City",
        location_text="Paris",
        raw_payload={
            "name": "Test Job",
            "applyUrl": "http://test",
            "location": {"city": "Paris", "region": "IDF", "country": "FR"}
        }
    )
    
    assert apply_backfill_to_job(job) is True
    assert job.location_city == "Paris"
    assert job.location_region == "IDF"


def test_ambiguous_remote_scope():
    """Test remote signals in location text."""
    job = Job(
        source="unknown_source",
        location_text="Remote - US",
        raw_payload={}
    )
    
    assert apply_backfill_to_job(job) is True
    assert job.location_workplace_type == WorkplaceType.remote
