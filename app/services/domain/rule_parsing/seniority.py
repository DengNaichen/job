"""Deterministic seniority inference rules for JD parsing."""

from __future__ import annotations


def infer_seniority_level(title: str | None, experience_years: int | None = None) -> str | None:
    """Infer seniority from title first, then years fallback."""
    lowered = (title or "").strip().lower()

    if lowered:
        patterns: list[tuple[str, tuple[str, ...]]] = [
            ("intern", ("intern", "internship")),
            ("principal", ("principal", "staff", "architect")),
            ("director", ("director", "head", "vice president", "vp", "chief")),
            ("manager", ("manager", "mgr")),
            ("lead", ("lead",)),
            ("senior", ("senior", "sr ", "sr.", "staff engineer")),
            ("junior", ("junior", "jr ", "jr.", "associate", "coordinator", "assistant")),
        ]
        for level, markers in patterns:
            if any(marker in lowered for marker in markers):
                return level

    if experience_years is None:
        return None
    if experience_years <= 1:
        return "junior"
    if experience_years >= 8:
        return "senior"
    if experience_years >= 5:
        return "mid"
    return "mid"


__all__ = ["infer_seniority_level"]
