"""
Greenhouse integration tests.

Usage:
    # Run all integration tests
    uv run pytest -m integration

    # Run only Greenhouse integration tests
    uv run pytest tests/integration/test_greenhouse_integration.py -v
"""

import pytest

from app.ingest.fetchers import GreenhouseFetcher
from app.ingest.mappers import GreenhouseMapper


@pytest.fixture
def fetcher():
    return GreenhouseFetcher()


@pytest.fixture
def mapper():
    return GreenhouseMapper()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_greenhouse_fetch_and_map(fetcher, mapper):
    """Integration test: fetch and map real API data."""
    # 1. Fetch real data (without content to reduce data size)
    jobs = await fetcher.fetch("airbnb", include_content=False)

    # Verify data was fetched
    assert len(jobs) > 0, "Should fetch job data"

    # 2. Map first 10 jobs to standard format
    mapped_count = 0
    errors = []

    for raw_job in jobs[:10]:
        try:
            result = mapper.map(raw_job)

            # Verify required fields
            assert result.source == "greenhouse"
            assert result.external_job_id, "external_job_id cannot be empty"
            assert result.title, "title cannot be empty"
            assert result.apply_url, "apply_url cannot be empty"

            # Verify raw_payload preserves original data
            assert result.raw_payload == raw_job

            mapped_count += 1

        except Exception as e:
            errors.append(f"Job {raw_job.get('id')}: {e}")

    # At least 90% should map successfully
    success_rate = mapped_count / min(len(jobs), 10)
    assert success_rate >= 0.9, f"Mapping success rate {success_rate:.1%} too low, errors: {errors}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_greenhouse_fetch_with_content(fetcher, mapper):
    """Integration test: fetch data with content."""
    jobs = await fetcher.fetch("airbnb", include_content=True)

    assert len(jobs) > 0

    # Check first job has description_html
    first_job = mapper.map(jobs[0])
    assert first_job.description_html is not None, (
        "Should have description when include_content=True"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_greenhouse_multiple_companies(fetcher, mapper):
    """Integration test: test multiple companies."""
    companies = ["airbnb", "stripe", "coinbase"]
    results = {}

    for company in companies:
        try:
            jobs = await fetcher.fetch(company, include_content=False)
            if len(jobs) > 0:
                # Map first job to verify
                mapped = mapper.map(jobs[0])
                results[company] = {
                    "total": len(jobs),
                    "sample_title": mapped.title,
                    "sample_url": mapped.apply_url,
                }
        except Exception as e:
            results[company] = {"error": str(e)}

    # At least 2 companies should succeed
    successful = sum(1 for r in results.values() if "error" not in r)
    assert successful >= 2, f"Only {successful} companies succeeded, results: {results}"
