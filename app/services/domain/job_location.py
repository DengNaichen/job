from dataclasses import dataclass
import re

import pycountry

from app.models.job import WorkplaceType
from app.models.location import Location
from app.repositories.job_location import JobLocationRepository
from app.repositories.location import LocationRepository
from app.services.domain.canonical_location import build_canonical_key, normalize_display_name
from app.services.domain.country_normalization import normalize_country
from app.services.domain.geonames_resolver import get_geonames_resolver
from sqlmodel.ext.asyncio.session import AsyncSession



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
    """
    Extract the workplace type from a list of text hints (e.g., location text, platform tags).
    Uses conservative keyword matching.
    """
    combined = " ".join(t.lower() for t in text_hints if t)
    if not combined:
        return default

    # Explicit remote signals
    if (
        "remote" in combined
        or "fully remote" in combined
        or "work from home" in combined
        or "telecommute" in combined
    ):
        return WorkplaceType.remote

    # Hybrid signals
    if "hybrid" in combined or "partially remote" in combined:
        return WorkplaceType.hybrid

    # Onsite signals
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
    """
    Conservatively parse a raw location string to extract structured elements.
    Uses regex and heuristics. Avoids generating false positives.
    """
    if not location_str:
        return StructuredLocation()

    loc = StructuredLocation()
    loc.workplace_type = extract_workplace_type([location_str])

    # Check for remote scope, e.g. "Remote - US", "Remote (EMEA)"
    lower_str = location_str.lower()
    if loc.workplace_type == WorkplaceType.remote:
        # Simplistic remote scope extraction
        # Match patterns like "Remote - [Scope]" or "Remote ([Scope])"
        scope_match = re.search(r"remote\s*[-–(]\s*([a-zA-Z\s,]+)[)]?", location_str, re.IGNORECASE)
        if scope_match:
            loc.remote_scope = scope_match.group(1).strip()

            # Since the role is remote with a scope, we also try to parse the scope as a country
            # Normalization returns ambiguity for things like "EMEA" which is correct
            country_res = normalize_country(loc.remote_scope, is_explicit_field=False)
            if country_res.country_code:
                loc.country_code = country_res.country_code

        # Some roles are just "US - Remote"
        elif "remote" in lower_str:
            parts = [p.strip() for p in re.split(r"[-–]", location_str)]
            for p in parts:
                if p.lower() != "remote":
                    country_res = normalize_country(p, is_explicit_field=False)
                    if country_res.country_code:
                        loc.country_code = country_res.country_code
                        loc.remote_scope = p
                        break

    # E.g., "San Francisco, CA" or "London, GB" or "Paris, France"
    # Basic comma splitting
    if not loc.country_code:
        parts = [p.strip() for p in location_str.split(",")]

        if len(parts) >= 2:
            # Let's see if the last part is a country
            country_res = normalize_country(parts[-1], is_explicit_field=False)
            if country_res.country_code:
                loc.country_code = country_res.country_code
                loc.city = parts[0]
                if len(parts) >= 3:
                    loc.region = parts[1]
                elif len(parts) == 2:
                    # Try GeoNames to recover region when country exists in text.
                    city_match = get_geonames_resolver().resolve_city(
                        city=parts[0], country_code=loc.country_code
                    )
                    if city_match and city_match.admin1_code:
                        loc.region = city_match.admin1_code
            else:
                region_hint = parts[1]
                city_match = get_geonames_resolver().resolve_city(
                    city=parts[0],
                    region=region_hint,
                )
                if city_match:
                    loc.city = parts[0]
                    loc.region = region_hint
                    loc.country_code = city_match.country_code
                elif len(parts[1]) == 2 and parts[1].isupper() and _is_us_state_code(parts[1]):
                    # Compatibility fallback when GeoNames reference data is unavailable.
                    loc.city = parts[0]
                    loc.region = parts[1]
                    loc.country_code = "US"
        elif len(parts) == 1:
            country_res = normalize_country(parts[0], is_explicit_field=False)
            if country_res.country_code:
                loc.country_code = country_res.country_code
            elif len(parts[0]) > 3:
                # City-only strings (e.g. "San Francisco") are resolved only if
                # GeoNames returns a high-confidence unique candidate.
                city_match = get_geonames_resolver().resolve_city(city=parts[0])
                if city_match:
                    loc.city = parts[0]
                    loc.region = city_match.admin1_code
                    loc.country_code = city_match.country_code

    return loc


async def sync_job_location(
    *,
    session: AsyncSession,
    job_id: str,
    structured: StructuredLocation,
    is_primary: bool = False,
    source_raw: str | None = None,
) -> Location:
    """
    Sync a structured location to a job.
    1. Generates a canonical key.
    2. Upserts the Location entity.
    3. Links the Location to the Job via JobLocation.
    """
    loc_repo = LocationRepository(session)
    job_loc_repo = JobLocationRepository(session)

    # Build canonical key for the location
    canonical_key = build_canonical_key(
        city=structured.city,
        region=structured.region,
        country_code=structured.country_code,
    )

    # Create Location model instance (Repositories handle existing check)
    location_data = Location(
        canonical_key=canonical_key,
        display_name=normalize_display_name(
            city=structured.city,
            region=structured.region,
            country_code=structured.country_code,
        ),
        city=structured.city,
        region=structured.region,
        country_code=structured.country_code,
    )

    # Upsert the location and link it
    location = await loc_repo.upsert(location_data)
    await job_loc_repo.link(
        job_id=job_id,
        location_id=location.id,
        is_primary=is_primary,
        source_raw=source_raw,
        workplace_type=structured.workplace_type.value,
        remote_scope=structured.remote_scope,
    )
    return location


