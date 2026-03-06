from dataclasses import dataclass

import pytest

from app.models.job import WorkplaceType
from app.services.domain.location import (
    extract_workplace_type,
    parse_location_text,
)


def test_extract_workplace_type() -> None:
    assert extract_workplace_type(["remote worker", ""]) == WorkplaceType.remote
    assert extract_workplace_type(["fully remote"]) == WorkplaceType.remote
    assert extract_workplace_type(["work from home"]) == WorkplaceType.remote
    assert extract_workplace_type(["office", "hybrid schedule"]) == WorkplaceType.hybrid
    assert extract_workplace_type(["onsite role"]) == WorkplaceType.onsite
    assert extract_workplace_type(["san francisco", "full-time"]) == WorkplaceType.unknown
    assert extract_workplace_type([], default=WorkplaceType.unknown) == WorkplaceType.unknown


def test_parse_location_text() -> None:
    loc = parse_location_text("San Francisco, CA")
    assert loc.city == "San Francisco"
    assert loc.region == "CA"
    assert loc.country_code == "US"
    assert loc.workplace_type == WorkplaceType.unknown

    loc2 = parse_location_text("Remote - CA")
    assert loc2.workplace_type == WorkplaceType.remote
    assert loc2.city is None

    loc3 = parse_location_text(None)
    assert loc3.city is None
    assert loc3.workplace_type == WorkplaceType.unknown

    loc4 = parse_location_text("London")
    assert loc4.city is None
    assert loc4.workplace_type == WorkplaceType.unknown


@dataclass
class _FakeGeoMatch:
    geonames_id: int
    name: str
    country_code: str
    admin1_code: str | None
    population: int


def test_parse_location_text_uses_geonames_for_region_name(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResolver:
        def resolve_city(self, *, city: str | None, region: str | None = None, country_code=None):
            _ = country_code
            if city == "San Francisco" and region == "California":
                return _FakeGeoMatch(
                    geonames_id=1,
                    name="San Francisco",
                    country_code="US",
                    admin1_code="CA",
                    population=100,
                )
            return None

    monkeypatch.setattr(
        "app.services.domain.location.parsing.get_geonames_resolver",
        lambda: _FakeResolver(),
    )

    loc = parse_location_text("San Francisco, California")
    assert loc.city == "San Francisco"
    assert loc.region == "California"
    assert loc.country_code == "US"


def test_parse_location_text_uses_geonames_for_city_only(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResolver:
        def resolve_city(self, *, city: str | None, region: str | None = None, country_code=None):
            _ = (region, country_code)
            if city == "Mexico City":
                return _FakeGeoMatch(
                    geonames_id=2,
                    name="Mexico City",
                    country_code="MX",
                    admin1_code="CMX",
                    population=100,
                )
            return None

    monkeypatch.setattr(
        "app.services.domain.location.parsing.get_geonames_resolver",
        lambda: _FakeResolver(),
    )

    loc = parse_location_text("Mexico City")
    assert loc.city == "Mexico City"
    assert loc.region == "CMX"
    assert loc.country_code == "MX"


class TestExplicitCountryAliasMapping:
    def test_location_ending_with_canada(self) -> None:
        loc = parse_location_text("Toronto, ON, Canada")
        assert loc.country_code == "CA"
        assert loc.city == "Toronto"
        assert loc.region == "ON"

    def test_location_ending_with_united_states(self) -> None:
        loc = parse_location_text("Austin, TX, United States")
        assert loc.country_code == "US"
        assert loc.city == "Austin"

    def test_location_ending_with_uk(self) -> None:
        loc = parse_location_text("London, UK")
        assert loc.country_code == "GB"
        assert loc.city == "London"

    def test_location_ending_with_germany(self) -> None:
        loc = parse_location_text("Berlin, Germany")
        assert loc.country_code == "DE"
        assert loc.city == "Berlin"

    def test_location_ending_with_japan(self) -> None:
        loc = parse_location_text("Tokyo, Japan")
        assert loc.country_code == "JP"
        assert loc.city == "Tokyo"


class TestCanonicalCodeOutput:
    def test_us_city_state_returns_us(self) -> None:
        loc = parse_location_text("San Francisco, CA")
        assert loc.country_code == "US"

    def test_country_name_returns_alpha2(self) -> None:
        loc = parse_location_text("Montreal, QC, Canada")
        assert loc.country_code == "CA"


class TestAmbiguousAbbreviations:
    def test_ca_in_us_city_state_context(self) -> None:
        loc = parse_location_text("San Francisco, CA")
        assert loc.country_code == "US"
        assert loc.region == "CA"

    def test_standalone_ca_is_ambiguous(self) -> None:
        loc = parse_location_text("CA")
        assert loc.country_code is None


class TestSingleCountryRemoteScope:
    def test_remote_dash_canada(self) -> None:
        loc = parse_location_text("Remote - Canada")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code == "CA"
        assert loc.remote_scope == "Canada"

    def test_remote_dash_us(self) -> None:
        loc = parse_location_text("Remote - United States")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code == "US"
        assert loc.remote_scope == "United States"

    def test_remote_paren_germany(self) -> None:
        loc = parse_location_text("Remote (Germany)")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code == "DE"
        assert loc.remote_scope == "Germany"


class TestMultiCountryRemoteScope:
    def test_remote_us_or_canada(self) -> None:
        loc = parse_location_text("Remote - US or Canada")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_us_and_uk(self) -> None:
        loc = parse_location_text("Remote - US and UK")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None


class TestSupranationalRegionCases:
    def test_remote_emea(self) -> None:
        loc = parse_location_text("Remote - EMEA")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_apac(self) -> None:
        loc = parse_location_text("Remote (APAC)")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_europe(self) -> None:
        loc = parse_location_text("Remote - Europe")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None

    def test_remote_north_america(self) -> None:
        loc = parse_location_text("Remote - North America")
        assert loc.workplace_type == WorkplaceType.remote
        assert loc.country_code is None
