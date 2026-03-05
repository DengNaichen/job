"""Deterministic sponsorship requirement extraction rules for JD parsing."""

from __future__ import annotations

from app.schemas.structured_jd import normalize_sponsorship


def extract_sponsorship(text: str) -> str:
    """Extract sponsorship availability from raw JD text."""
    return normalize_sponsorship(text)


__all__ = ["extract_sponsorship"]
