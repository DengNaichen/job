import re
import unicodedata


def build_canonical_key(city: str | None, region: str | None, country_code: str | None) -> str:
    """
    Build a deterministic lowercase slug: {country}-{region}-{city}.
    Normalizes unicode, strips special chars, and joins with hyphens.
    """
    parts = []
    if country_code:
        parts.append(country_code.lower())
    if region:
        parts.append(region.lower())
    if city:
        parts.append(city.lower())

    if not parts:
        return "unknown"

    normalized_parts = []
    for part in parts:
        part = part.replace("-", " ")
        normalized = unicodedata.normalize("NFKD", part).encode("ASCII", "ignore").decode("ASCII")
        normalized = re.sub(r"[^a-z0-9\s]", "", normalized.lower())
        normalized = re.sub(r"\s+", "-", normalized.strip())
        if normalized:
            normalized_parts.append(normalized)

    if not normalized_parts:
        return "unknown"

    return "-".join(normalized_parts)


def normalize_display_name(city: str | None, region: str | None, country_code: str | None) -> str:
    """Build a human-readable display name, e.g. 'San Francisco, CA, US'."""
    parts = []
    if city:
        parts.append(city)
    if region:
        parts.append(region)
    if country_code:
        parts.append(country_code.upper())

    if not parts:
        return "Unknown Location"

    return ", ".join(parts)
