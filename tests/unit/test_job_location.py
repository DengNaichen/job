from app.models.job import Job, WorkplaceType
from app.services.domain.job_location import (
    StructuredLocation,
    extract_workplace_type,
    parse_location_text,
    sync_job_location,
    sync_primary_to_job,
)
from sqlmodel.ext.asyncio.session import AsyncSession
import pytest


def test_extract_workplace_type():
    assert extract_workplace_type(["remote worker", ""]) == WorkplaceType.remote
    assert extract_workplace_type(["fully remote"]) == WorkplaceType.remote
    assert extract_workplace_type(["work from home"]) == WorkplaceType.remote
    assert extract_workplace_type(["office", "hybrid schedule"]) == WorkplaceType.hybrid
    assert extract_workplace_type(["onsite role"]) == WorkplaceType.onsite
    assert extract_workplace_type(["san francisco", "full-time"]) == WorkplaceType.unknown
    assert extract_workplace_type([], default=WorkplaceType.unknown) == WorkplaceType.unknown


def test_parse_location_text():
    # Regular US City, State
    loc = parse_location_text("San Francisco, CA")
    assert loc.city == "San Francisco"
    assert loc.region == "CA"
    assert loc.country_code == "US"
    assert loc.workplace_type == WorkplaceType.unknown

    # Remote indication
    loc2 = parse_location_text("Remote - CA")
    assert loc2.workplace_type == WorkplaceType.remote
    assert loc2.city is None

    # None case
    loc3 = parse_location_text(None)
    assert loc3.city is None
    assert loc3.workplace_type == WorkplaceType.unknown

    # Just city
    loc4 = parse_location_text("London")
    assert loc4.city is None  # Since naive logic checks len(parts) >= 2
    assert loc4.workplace_type == WorkplaceType.unknown


# ---------------------------------------------------------------------------
# T005: Extended coverage for canonical country normalization
# ---------------------------------------------------------------------------


class TestExplicitCountryAliasMapping:
    """Verify that explicit country alias strings produce canonical alpha-2 codes
    when parsed through location text that ends with a recognizable country."""

    def test_location_ending_with_canada(self):
        loc = parse_location_text("Toronto, ON, Canada")
        assert loc.country_code == "CA"
        assert loc.city == "Toronto"
        assert loc.region == "ON"

    def test_location_ending_with_united_states(self):
        loc = parse_location_text("Austin, TX, United States")
        assert loc.country_code == "US"
        assert loc.city == "Austin"

    def test_location_ending_with_uk(self):
        loc = parse_location_text("London, UK")
        assert loc.country_code == "GB"
        assert loc.city == "London"

    def test_location_ending_with_germany(self):
        loc = parse_location_text("Berlin, Germany")
        assert loc.country_code == "DE"
        assert loc.city == "Berlin"

    def test_location_ending_with_japan(self):
        loc = parse_location_text("Tokyo, Japan")
        assert loc.country_code == "JP"
        assert loc.city == "Tokyo"


class TestCanonicalCodeOutput:
    """Confirm final output is always uppercase ISO 3166-1 alpha-2."""

    def test_us_city_state_returns_us(self):
        loc = parse_location_text("San Francisco, CA")
        assert loc.country_code == "US"

    def test_country_name_returns_alpha2(self):
        loc = parse_location_text("Montreal, QC, Canada")
        assert loc.country_code == "CA"  # alpha-2, not "Canada"


class TestAmbiguousAbbreviations:
    """CA as a state abbreviation MUST NOT be misinterpreted as Canada."""

    def test_ca_in_us_city_state_context(self):
        """San Francisco, CA should resolve to US, not Canada."""
        loc = parse_location_text("San Francisco, CA")
        assert loc.country_code == "US"
        assert loc.region == "CA"

    def test_standalone_ca_is_ambiguous(self):
        """A bare 'CA' in non-explicit text is ambiguous — should not become a country."""
        loc = parse_location_text("CA")
        assert loc.country_code is None


class TestSingleCountryRemoteScope:
    """Remote jobs scoped to exactly one country should populate country_code."""

    def test_remote_dash_canada(self):
        loc = parse_location_text("Remote - Canada")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code == "CA"
        assert loc.remote_scope == "Canada"

    def test_remote_dash_us(self):
        loc = parse_location_text("Remote - United States")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code == "US"
        assert loc.remote_scope == "United States"

    def test_remote_paren_germany(self):
        loc = parse_location_text("Remote (Germany)")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code == "DE"
        assert loc.remote_scope == "Germany"


class TestMultiCountryRemoteScope:
    """Remote jobs covering multiple countries must leave country_code null."""

    def test_remote_us_or_canada(self):
        loc = parse_location_text("Remote - US or Canada")
        assert loc.workplace_type == WorkplaceType.remote
        # Multi-country scope — country_code should be None
        assert loc.country_code is None

    def test_remote_us_and_uk(self):
        loc = parse_location_text("Remote - US and UK")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None


class TestSupranationalRegionCases:
    """Region labels like EMEA, APAC must not resolve to a country code."""

    def test_remote_emea(self):
        loc = parse_location_text("Remote - EMEA")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_apac(self):
        loc = parse_location_text("Remote (APAC)")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_europe(self):
        loc = parse_location_text("Remote - Europe")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_north_america(self):
        loc = parse_location_text("Remote - North America")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None


# ---------------------------------------------------------------------------
# US1: Database-backed sync tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_job_location_idempotency(session: AsyncSession):
    # Setup job
    job = Job(
        source="lever",
        external_job_id="test-123",
        title="Software Engineer",
        apply_url="https://example.com",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    structured = StructuredLocation(
        city="San Francisco",
        region="CA",
        country_code="US",
        workplace_type=WorkplaceType.onsite,
    )

    # First sync
    loc1 = await sync_job_location(
        session=session,
        job_id=job.id,
        structured=structured,
        is_primary=True,
        source_raw="San Francisco, CA",
    )

    assert loc1.canonical_key == "us-ca-san-francisco"

    # Second sync (identical)
    loc2 = await sync_job_location(
        session=session,
        job_id=job.id,
        structured=structured,
        is_primary=True,
        source_raw="San Francisco, CA",
    )

    assert loc1.id == loc2.id


@pytest.mark.asyncio
async def test_sync_primary_to_job_compatibility(session: AsyncSession):
    job = Job(
        source="lever",
        external_job_id="test-456",
        title="Data Scientist",
        apply_url="https://example.com",
    )

    structured = StructuredLocation(
        city="Seattle",
        region="WA",
        country_code="US",
        workplace_type=WorkplaceType.hybrid,
    )

    # Sync to DB first to get Location object
    location = await sync_job_location(
        session=session,
        job_id="dummy",  # Not linked to real job yet in this test part
        structured=structured,
        is_primary=True,
    )

    sync_primary_to_job(
        job=job,
        location=location,
        workplace_type=structured.workplace_type,
    )

    assert job.location_city == "Seattle"
    assert job.location_region == "WA"
    assert job.location_country_code == "US"
    assert job.location_workplace_type == WorkplaceType.hybrid
