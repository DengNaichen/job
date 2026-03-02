from dataclasses import dataclass
import re

from app.models.job import WorkplaceType
from app.services.domain.country_normalization import normalize_country


@dataclass
class StructuredLocation:
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    workplace_type: WorkplaceType = WorkplaceType.unknown
    remote_scope: str | None = None


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
                if len(parts) == 3:
                    loc.region = parts[1]
                elif len(parts) == 2 and not country_res.country_code:
                    # check if parts[1] is a 2-letter state code, very naive check
                    if len(parts[1]) == 2 and parts[1].isupper():
                        loc.city = parts[0]
                        loc.region = parts[1]
                        loc.country_code = "US"
            else:
                # Retain existing naive behavior
                if len(parts[1]) == 2 and parts[1].isupper():
                    loc.city = parts[0]
                    loc.region = parts[1]
                    loc.country_code = "US"
        elif len(parts) == 1:
            country_res = normalize_country(parts[0], is_explicit_field=False)
            if country_res.country_code:
                loc.country_code = country_res.country_code

    return loc
