import re
from typing import TypedDict
from dataclasses import dataclass

from app.models.job import WorkplaceType


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
    if "remote" in combined or "fully remote" in combined or "work from home" in combined or "telecommute" in combined:
        return WorkplaceType.remote
    
    # Hybrid signals
    if "hybrid" in combined or "partially remote" in combined:
        return WorkplaceType.hybrid
    
    # Onsite signals
    if "onsite" in combined or "on-site" in combined or "in office" in combined or "in-office" in combined:
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

    # Simple comma splitting: "City, State, Country" or "City, State"
    # Note: we only extract with high confidence patterns (e.g. US States)
    parts = [p.strip() for p in location_str.split(",")]
    
    # E.g., "San Francisco, CA"
    # Very basic, to be improved iteratively inside mappers or with a good library
    if len(parts) >= 2:
        # Check if parts[1] is a 2-letter state code, very naive check
        if len(parts[1]) == 2 and parts[1].isupper():
            loc.city = parts[0]
            loc.region = parts[1]
            loc.country_code = "US"  # Assumption for 2 uppercase letters region in typical ATS defaults, can be scoped
        
    return loc
