"""Normalization helpers for skill text."""

from __future__ import annotations

import re


def normalize_skill_text(value: str | None) -> str:
    """Normalize skill text for deterministic exact matching."""
    if value is None:
        return ""
    lowered = value.strip().lower()
    lowered = lowered.replace("&", " and ")
    lowered = re.sub(r"[_/.-]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


__all__ = ["normalize_skill_text"]

