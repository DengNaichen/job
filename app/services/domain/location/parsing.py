from dataclasses import dataclass
import re

import pycountry

from app.models.job import WorkplaceType
from app.services.domain.location.resolution import get_geonames_resolver, normalize_country


@dataclass
class StructuredLocation:
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    workplace_type: WorkplaceType = WorkplaceType.unknown
    remote_scope: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.workplace_type, str):
            try:
                self.workplace_type = WorkplaceType(self.workplace_type)
            except ValueError:
                self.workplace_type = WorkplaceType.unknown


def extract_workplace_type(
    text_hints: list[str | None], *, default: WorkplaceType = WorkplaceType.unknown
) -> WorkplaceType:
    """Extract a conservative workplace type from free-text hints."""
    combined = " ".join(text.lower() for text in text_hints if text)
    if not combined:
        return default

    if (
        "remote" in combined
        or "fully remote" in combined
        or "work from home" in combined
        or "telecommute" in combined
    ):
        return WorkplaceType.remote

    if "hybrid" in combined or "partially remote" in combined:
        return WorkplaceType.hybrid

    if (
        "onsite" in combined
        or "on-site" in combined
        or "in office" in combined
        or "in-office" in combined
    ):
        return WorkplaceType.onsite

    return default


def _is_us_state_code(value: str | None) -> bool:
    code = (value or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return False
    try:
        return pycountry.subdivisions.get(code=f"US-{code}") is not None
    except Exception:
        return False


def parse_location_text(location_str: str | None) -> StructuredLocation:
    """Conservatively parse raw location text into a structured location."""
    if not location_str:
        return StructuredLocation()

    location = StructuredLocation()
    location.workplace_type = extract_workplace_type([location_str])

    lower_str = location_str.lower()
    if location.workplace_type == WorkplaceType.remote:
        scope_match = re.search(
            r"remote\s*[-–(]\s*([a-zA-Z\s,]+)[)]?",
            location_str,
            re.IGNORECASE,
        )
        if scope_match:
            location.remote_scope = scope_match.group(1).strip()
            country_result = normalize_country(location.remote_scope, is_explicit_field=False)
            if country_result.country_code:
                location.country_code = country_result.country_code
        elif "remote" in lower_str:
            parts = [part.strip() for part in re.split(r"[-–]", location_str)]
            for part in parts:
                if part.lower() == "remote":
                    continue
                country_result = normalize_country(part, is_explicit_field=False)
                if country_result.country_code:
                    location.country_code = country_result.country_code
                    location.remote_scope = part
                    break

    if not location.country_code:
        parts = [part.strip() for part in location_str.split(",")]

        if len(parts) >= 2:
            country_result = normalize_country(parts[-1], is_explicit_field=False)
            if country_result.country_code:
                location.country_code = country_result.country_code
                location.city = parts[0]
                if len(parts) >= 3:
                    location.region = parts[1]
                elif len(parts) == 2:
                    city_match = get_geonames_resolver().resolve_city(
                        city=parts[0],
                        country_code=location.country_code,
                    )
                    if city_match and city_match.admin1_code:
                        location.region = city_match.admin1_code
            else:
                region_hint = parts[1]
                city_match = get_geonames_resolver().resolve_city(
                    city=parts[0],
                    region=region_hint,
                )
                if city_match:
                    location.city = parts[0]
                    location.region = region_hint
                    location.country_code = city_match.country_code
                elif len(parts[1]) == 2 and parts[1].isupper() and _is_us_state_code(parts[1]):
                    location.city = parts[0]
                    location.region = parts[1]
                    location.country_code = "US"
        elif len(parts) == 1:
            country_result = normalize_country(parts[0], is_explicit_field=False)
            if country_result.country_code:
                location.country_code = country_result.country_code
            elif len(parts[0]) > 3:
                city_match = get_geonames_resolver().resolve_city(city=parts[0])
                if city_match:
                    location.city = parts[0]
                    location.region = city_match.admin1_code
                    location.country_code = city_match.country_code

    return location
