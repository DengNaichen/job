from app.models.job import Job, WorkplaceType
from scripts.backfill_job_locations import apply_backfill_to_job


def test_apply_backfill_high_confidence():
    """High confidence raw payload should populate fields where they are missing."""
    job = Job(
        source="smartrecruiters",
        raw_payload={
            "name": "Test Job",
            "applyUrl": "http://test",
            "location": {"city": "Paris", "region": "IDF", "country": "FR", "remote": True},
        },
        location_text="France",
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
        location_text="San Francisco, CA",
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
            "location": {"city": "Paris", "region": "IDF", "country": "FR"},
        },
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
        raw_payload={
            "title": "Test",
            "applyUrl": "http://test",
        },  # Will trigger ashby mapper which uses parse_location_text (low confidence)
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
            "location": {"city": "Paris", "region": "IDF", "country": "FR"},
        },
    )

    assert apply_backfill_to_job(job) is True
    assert job.location_city == "Paris"
    assert job.location_region == "IDF"


def test_ambiguous_remote_scope():
    """Test remote signals in location text."""
    job = Job(source="unknown_source", location_text="Remote - US", raw_payload={})

    assert apply_backfill_to_job(job) is True
    assert job.location_workplace_type == WorkplaceType.remote


def test_apply_backfill_country_canonicalization():
    """Should upgrade raw country names and codes to canonical alpha-2."""
    # Test case 1: Raw country name in payload (High Confidence)
    job = Job(
        source="smartrecruiters",
        raw_payload={
            "name": "Engineer",
            "applyUrl": "http://example.com",
            "location": {"city": "Toronto", "country": "Canada"},
        },
        location_country_code=None,
    )
    assert apply_backfill_to_job(job) is True
    assert job.location_country_code == "CA"

    # Test case 2: Raw country name in location_text fallback (Heuristic)
    job = Job(
        source="unknown",
        location_text="London, United Kingdom",
        location_country_code=None,
        raw_payload={},
    )
    assert apply_backfill_to_job(job) is True
    assert job.location_country_code == "GB"


def test_apply_backfill_remote_scope_canonicalization():
    """Should extract country from location_remote_scope."""
    job = Job(
        source="unknown",
        location_workplace_type=WorkplaceType.remote,
        location_remote_scope="Canada",
        location_country_code=None,
        raw_payload={},
    )
    assert apply_backfill_to_job(job) is True
    assert job.location_country_code == "CA"


def test_apply_backfill_protect_canonical_country():
    """Should NOT overwrite an already-canonical country with lower-confidence parse."""
    job = Job(
        source="unknown",
        location_country_code="FR",
        location_city="Paris",  # Pre-populate city so it doesn't trigger 'changed'
        location_text="London, UK",  # Suggests GB
        raw_payload={},
    )
    # Even though location_text implies GB, current is already canonical (FR)
    # and we have no high-confidence (mapper) data to override it.
    assert apply_backfill_to_job(job) is False
    assert job.location_country_code == "FR"


def test_apply_backfill_upgrade_non_canonical_country():
    """Should overwrite a non-canonical (raw name) country even with lower-confidence parse."""
    job = Job(
        source="unknown",
        location_country_code="Canada",  # Raw string, not canonical code
        location_text="Toronto, Canada",
        raw_payload={},
    )
    assert apply_backfill_to_job(job) is True
    assert job.location_country_code == "CA"
