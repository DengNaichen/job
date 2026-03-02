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

    # Normalize each part
    normalized_parts = []
    for p in parts:
        # Replace hyphens with spaces to treat them as word separators
        p = p.replace("-", " ")
        # Unicode normalize and remove accents
        n = unicodedata.normalize("NFKD", p).encode("ASCII", "ignore").decode("ASCII")
        # Remove non-alphanumeric except spaces
        n = re.sub(r"[^a-z0-9\s]", "", n.lower())
        # Replace spaces with hyphens
        n = re.sub(r"\s+", "-", n.strip())
        if n:
            normalized_parts.append(n)

    if not normalized_parts:
        return "unknown"

    # Ensure uniqueness if some parts are identical or blank
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
