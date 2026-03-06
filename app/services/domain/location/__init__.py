"""Location domain parsing, resolution, and canonicalization."""

from app.services.domain.location.canonical import build_canonical_key, normalize_display_name
from app.services.domain.location.parsing import (
    StructuredLocation,
    extract_workplace_type,
    parse_location_text,
)
from app.services.domain.location.resolution import (
    ConfidenceScore,
    CountryNormalizationResult,
    GeoNamesCityCandidate,
    GeoNamesResolver,
    SourceMethod,
    get_geonames_resolver,
    is_canonical_country_code,
    normalize_country,
)

__all__ = [
    "ConfidenceScore",
    "CountryNormalizationResult",
    "GeoNamesCityCandidate",
    "GeoNamesResolver",
    "SourceMethod",
    "StructuredLocation",
    "build_canonical_key",
    "extract_workplace_type",
    "get_geonames_resolver",
    "is_canonical_country_code",
    "normalize_country",
    "normalize_display_name",
    "parse_location_text",
]
