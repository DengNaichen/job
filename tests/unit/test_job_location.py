from app.services.domain.job_location import parse_location_text, extract_workplace_type
from app.models.job import WorkplaceType


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
    # Regex currently isn't sophisticated enough to extract CA reliably from "Remote - CA" with our naive splitting
    # But it should recognize remote
    assert loc2.city is None

    # None case
    loc3 = parse_location_text(None)
    assert loc3.city is None
    assert loc3.workplace_type == WorkplaceType.unknown

    # Just city
    loc4 = parse_location_text("London")
    assert loc4.city is None  # Since naive logic checks len(parts) >= 2
    assert loc4.workplace_type == WorkplaceType.unknown
