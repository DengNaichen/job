import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import pycountry

from app.services.domain.geonames_resolver import get_geonames_resolver


class ConfidenceScore(str, Enum):
    HIGH = "high"
    LOW = "low"
    NONE = "none"


class SourceMethod(str, Enum):
    EXPLICIT_FIELD = "explicit_field"
    GEONAMES_MATCH = "geonames_match"
    PYCOUNTRY_MATCH = "pycountry_match"
    UNKNOWN = "unknown"


@dataclass
class CountryNormalizationResult:
    country_code: Optional[str] = None
    confidence: ConfidenceScore = ConfidenceScore.NONE
    source: SourceMethod = SourceMethod.UNKNOWN
    is_ambiguous: bool = False
    multi_country_detected: bool = False
    matched_country_codes: List[str] = field(default_factory=list)


# Ambiguous and broad regions that shouldn't match as single countries
AMBIGUOUS_REGIONS = {
    "remote",
    "global",
    "europe",
    "eu",
    "asia",
    "apac",
    "emea",
    "latam",
    "america",
    "americas",
    "north america",
    "south america",
    "africa",
    "anywhere",
}

# Common sub-regions (like US states, Canadian provinces) that collide with ISO 3166-1 alpha-2 codes
# If we encounter these in non-explicit fields, we treat them as ambiguous.
AMBIGUOUS_ALPHA2 = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "PR",
    # Canada
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}

# ISO 3166 exceptional reservations that appear in real-world feeds.
# These are not canonical alpha-2 but can be normalized deterministically.
ISO_EXCEPTIONAL_ALPHA2 = {
    "UK": "GB",
}


def normalize_country(
    text: str | None, is_explicit_field: bool = False
) -> CountryNormalizationResult:
    """
    Normalizes a raw country string or location string into an ISO-3166-1 alpha-2 code.

    Args:
        text: The raw string to normalize.
        is_explicit_field: True if the text came from a dedicated "country" field.
    """
    if not text:
        return CountryNormalizationResult()

    original_text = text.strip()
    text_lower = original_text.lower()

    if text_lower in AMBIGUOUS_REGIONS:
        return CountryNormalizationResult(is_ambiguous=True)

    alpha_lookup = text_lower.upper()
    compact_alpha = re.sub(r"[^A-Z]", "", alpha_lookup)

    if compact_alpha in ISO_EXCEPTIONAL_ALPHA2:
        normalized = ISO_EXCEPTIONAL_ALPHA2[compact_alpha]
        return CountryNormalizationResult(
            country_code=normalized,
            confidence=ConfidenceScore.HIGH if is_explicit_field else ConfidenceScore.LOW,
            source=SourceMethod.PYCOUNTRY_MATCH
            if not is_explicit_field
            else SourceMethod.EXPLICIT_FIELD,
            matched_country_codes=[normalized],
        )

    if len(alpha_lookup) == 2 and alpha_lookup.isalpha() and not is_explicit_field:
        # Non-explicit alpha-2 tokens like "CA"/"ON" are often state/province abbreviations.
        if alpha_lookup in AMBIGUOUS_ALPHA2:
            return CountryNormalizationResult(is_ambiguous=True)

    geonames_codes = sorted(get_geonames_resolver().lookup_country_codes(original_text))
    if len(geonames_codes) == 1:
        return CountryNormalizationResult(
            country_code=geonames_codes[0],
            confidence=ConfidenceScore.HIGH if is_explicit_field else ConfidenceScore.LOW,
            source=SourceMethod.GEONAMES_MATCH
            if not is_explicit_field
            else SourceMethod.EXPLICIT_FIELD,
            matched_country_codes=geonames_codes,
        )
    if len(geonames_codes) > 1:
        return CountryNormalizationResult(
            is_ambiguous=True,
            multi_country_detected=True,
            matched_country_codes=geonames_codes,
        )

    # Check pycountry strict matches (alpha-2, alpha-3)
    try:
        country = None
        if len(alpha_lookup) == 2 and alpha_lookup.isalpha():
            country = pycountry.countries.get(alpha_2=alpha_lookup)

        elif len(alpha_lookup) == 3 and alpha_lookup.isalpha():
            country = pycountry.countries.get(alpha_3=alpha_lookup)

        if country:
            return CountryNormalizationResult(
                country_code=country.alpha_2,
                confidence=ConfidenceScore.HIGH if is_explicit_field else ConfidenceScore.LOW,
                source=SourceMethod.PYCOUNTRY_MATCH
                if not is_explicit_field
                else SourceMethod.EXPLICIT_FIELD,
                matched_country_codes=[country.alpha_2],
            )
    except Exception:
        pass

    # Explicit country fields can use fuzzy matching safely because caller intent
    # is "this token is a country". We still reject multi-match ambiguity.
    if is_explicit_field:
        try:
            fuzzy_codes = sorted({c.alpha_2 for c in pycountry.countries.search_fuzzy(original_text)})
            if len(fuzzy_codes) == 1:
                return CountryNormalizationResult(
                    country_code=fuzzy_codes[0],
                    confidence=ConfidenceScore.HIGH,
                    source=SourceMethod.EXPLICIT_FIELD,
                    matched_country_codes=fuzzy_codes,
                )
        except Exception:
            pass

    # Name lookup (case-insensitive)
    matched_countries = []
    for c in pycountry.countries:
        try:
            if text_lower == c.name.lower() or (
                hasattr(c, "official_name") and text_lower == c.official_name.lower()
            ):
                matched_countries.append(c.alpha_2)
        except AttributeError:
            continue

    if len(matched_countries) == 1:
        return CountryNormalizationResult(
            country_code=matched_countries[0],
            confidence=ConfidenceScore.HIGH if is_explicit_field else ConfidenceScore.LOW,
            source=SourceMethod.PYCOUNTRY_MATCH
            if not is_explicit_field
            else SourceMethod.EXPLICIT_FIELD,
            matched_country_codes=matched_countries,
        )
    elif len(matched_countries) > 1:
        return CountryNormalizationResult(
            is_ambiguous=True, multi_country_detected=True, matched_country_codes=matched_countries
        )

    # Multi-country detection for comma- or 'and'-separated strings
    if is_explicit_field and ("," in text_lower or " and " in text_lower or "/" in text_lower):
        parts = re.split(r",|\band\b|/", text_lower)
        found_codes = set()
        for p in parts:
            res = normalize_country(p, is_explicit_field=False)
            if res.country_code:
                found_codes.add(res.country_code)

        if found_codes:
            if len(found_codes) == 1:
                return CountryNormalizationResult(
                    country_code=list(found_codes)[0],
                    confidence=ConfidenceScore.HIGH,
                    source=SourceMethod.EXPLICIT_FIELD,
                    matched_country_codes=list(found_codes),
                )
            else:
                return CountryNormalizationResult(
                    multi_country_detected=True,
                    is_ambiguous=True,
                    matched_country_codes=list(found_codes),
                )

    return CountryNormalizationResult()


def is_canonical_country_code(value: str | None) -> bool:
    """Return True if *value* is a valid ISO 3166-1 alpha-2 country code.

    Used by backfill logic to decide whether an existing
    ``location_country_code`` is already canonical and should be protected
    from lower-confidence overwrites.
    """
    if not value or not isinstance(value, str):
        return False
    upper = value.strip().upper()
    if len(upper) != 2 or not upper.isalpha():
        return False
    return pycountry.countries.get(alpha_2=upper) is not None
