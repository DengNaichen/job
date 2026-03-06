from app.services.domain.location.canonical import build_canonical_key, normalize_display_name


def test_build_canonical_key_basic():
    assert build_canonical_key("San Francisco", "CA", "US") == "us-ca-san-francisco"
    assert build_canonical_key("London", None, "GB") == "gb-london"
    assert build_canonical_key(None, None, "US") == "us"


def test_build_canonical_key_normalization():
    # Accents and case
    assert build_canonical_key("Montréal", "QC", "CA") == "ca-qc-montreal"
    # Special characters and spaces
    assert build_canonical_key("New-York", "N.Y.", "US") == "us-ny-new-york"
    assert build_canonical_key("San Francisco ", " CA ", "US") == "us-ca-san-francisco"


def test_build_canonical_key_empty():
    assert build_canonical_key(None, None, None) == "unknown"
    assert build_canonical_key("", "", "") == "unknown"


def test_normalize_display_name():
    assert normalize_display_name("San Francisco", "CA", "US") == "San Francisco, CA, US"
    assert normalize_display_name("London", None, "GB") == "London, GB"
    assert normalize_display_name(None, None, "US") == "US"
    assert normalize_display_name(None, None, None) == "Unknown Location"
