"""Matching helpers for offline experiments and future API use."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.schemas.structured_jd import (
    degree_level_to_rank,
    normalize_degree_level,
    normalize_job_domain_name,
)
from app.services.domain.jd_rules import infer_seniority_level

_SKILL_TOKEN_RE = re.compile(r"[^a-z0-9]+")

_SENIORITY_RANK: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "manager": 4,
    "director": 5,
    "principal": 5,
}

_ADJACENT_JOB_DOMAINS: dict[str, set[str]] = {
    "software_engineering": {"data_ai", "product_program"},
    "data_ai": {"software_engineering", "operations", "finance_treasury"},
    "product_program": {"software_engineering", "operations"},
    "finance_treasury": {"operations", "data_ai"},
    "operations": {"finance_treasury", "data_ai", "product_program", "marketing_growth"},
    "marketing_growth": {"sales_account_management", "operations"},
    "sales_account_management": {"marketing_growth"},
}


def to_int(value: object, default: int = 0) -> int:
    """Best-effort integer parsing."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(float(stripped))
        except ValueError:
            return default
    return default


def to_optional_int(value: object) -> int | None:
    """Best-effort integer parsing that preserves missing values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def infer_needs_sponsorship(user_data: dict[str, Any], override: str = "auto") -> bool:
    """Infer whether the user needs employer sponsorship."""
    if override == "true":
        return True
    if override == "false":
        return False

    value = user_data.get("workAuthorization")
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False

    yes_markers = (
        "need sponsorship",
        "requires sponsorship",
        "require sponsorship",
        "h1b",
        "opt",
        "visa required",
    )
    no_markers = (
        "no sponsorship",
        "does not require sponsorship",
        "authorized",
        "citizen",
        "green card",
        "permanent resident",
    )
    if any(marker in text for marker in yes_markers):
        return True
    if any(marker in text for marker in no_markers):
        return False
    return False


def infer_user_degree_rank(user_data: dict[str, Any]) -> int:
    """Infer highest degree rank from the user's education list."""
    education = user_data.get("education", [])
    if not isinstance(education, list):
        return -1

    max_rank = -1
    for item in education:
        if not isinstance(item, dict):
            continue
        degree = item.get("degree")
        rank = degree_level_to_rank(normalize_degree_level(degree))
        if rank > max_rank:
            max_rank = rank
    return max_rank


def build_user_embedding_text(user_data: dict[str, Any], max_chars: int) -> str:
    """Build a stable embedding string from user summary, skills, and work history."""
    summary = str(user_data.get("summary") or "").strip()

    skills = user_data.get("skills", [])
    if isinstance(skills, list):
        skills_text = ", ".join(str(x).strip() for x in skills if str(x).strip())
    else:
        skills_text = str(skills).strip()

    bullets: list[str] = []
    work_history = user_data.get("workHistory", [])
    if isinstance(work_history, list):
        for item in work_history:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            company = str(item.get("company") or "").strip()
            item_bullets = item.get("bullets", [])
            if isinstance(item_bullets, list):
                joined_bullets = " ".join(str(x).strip() for x in item_bullets if str(x).strip())
            else:
                joined_bullets = str(item_bullets or "").strip()
            segment = " | ".join(part for part in (title, company, joined_bullets) if part)
            if segment:
                bullets.append(segment)

    text = (
        "User Summary:\n"
        f"{summary}\n\n"
        "Skills:\n"
        f"{skills_text}\n\n"
        "Work Highlights:\n" + "\n".join(f"- {b}" for b in bullets)
    ).strip()

    if len(text) > max_chars:
        return text[:max_chars]
    return text


def _normalize_skill_token(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = _SKILL_TOKEN_RE.sub(" ", text)
    return " ".join(text.split())


def _collect_skill_tokens(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {token for item in values if (token := _normalize_skill_token(item))}


def _parse_structured_jd_payload(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def build_user_skill_tokens(user_data: dict[str, Any]) -> set[str]:
    """Build normalized skill tokens from the user's explicit skill list."""
    return _collect_skill_tokens(user_data.get("skills", []))


def infer_user_job_domain(user_data: dict[str, Any]) -> str:
    """Infer a coarse user domain from summary, skills, and recent titles."""
    votes: Counter[str] = Counter()

    summary = str(user_data.get("summary") or "").strip()
    summary_domain = normalize_job_domain_name(summary)
    if summary_domain != "unknown":
        votes[summary_domain] += 2

    skills = user_data.get("skills", [])
    if isinstance(skills, list):
        for item in skills:
            domain = normalize_job_domain_name(item)
            if domain != "unknown":
                votes[domain] += 1

    work_history = user_data.get("workHistory", [])
    if isinstance(work_history, list):
        for item in work_history:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            domain = normalize_job_domain_name(title)
            if domain != "unknown":
                votes[domain] += 3

    if not votes:
        return "unknown"
    return votes.most_common(1)[0][0]


def infer_user_seniority_level(user_data: dict[str, Any]) -> str | None:
    """Infer a coarse seniority level from total years experience."""
    years = to_optional_int(user_data.get("totalYearsExperience"))
    if years is None:
        work_history = user_data.get("workHistory", [])
        if isinstance(work_history, list):
            for item in work_history:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                level = infer_seniority_level(title, None)
                if level:
                    return level
        return None
    if years <= 1:
        return "junior"
    if years <= 4:
        return "mid"
    if years <= 8:
        return "senior"
    return "director"


def compute_skill_overlap_score(
    *,
    user_skill_tokens: set[str],
    required_skills: list[str],
    preferred_skills: list[str],
) -> float:
    """Compute a normalized skill overlap score in the range [0, 1]."""
    weighted_score = 0.0
    total_weight = 0.0

    required_tokens = _collect_skill_tokens(required_skills)
    if required_tokens:
        required_overlap = len(required_tokens & user_skill_tokens) / len(required_tokens)
        weighted_score += 0.7 * required_overlap
        total_weight += 0.7

    preferred_tokens = _collect_skill_tokens(preferred_skills)
    if preferred_tokens:
        preferred_overlap = len(preferred_tokens & user_skill_tokens) / len(preferred_tokens)
        weighted_score += 0.3 * preferred_overlap
        total_weight += 0.3

    if total_weight == 0:
        return 0.0
    return weighted_score / total_weight


def compute_domain_match_score(
    *,
    user_domain: str,
    job_domain: str,
) -> float:
    """Compute a domain affinity score in the range [0, 1]."""
    if user_domain == "unknown" or job_domain == "unknown":
        return 0.0
    if user_domain == job_domain:
        return 1.0
    if job_domain in _ADJACENT_JOB_DOMAINS.get(
        user_domain, set()
    ) or user_domain in _ADJACENT_JOB_DOMAINS.get(job_domain, set()):
        return 0.5
    return 0.0


def compute_seniority_match_score(
    *,
    user_seniority: str | None,
    job_seniority: str | None,
) -> float:
    """Compute a seniority affinity score in the range [0, 1]."""
    if not user_seniority or not job_seniority:
        return 0.0

    user_rank = _SENIORITY_RANK.get(user_seniority)
    job_rank = _SENIORITY_RANK.get(job_seniority)
    if user_rank is None or job_rank is None:
        return 0.0

    distance = abs(user_rank - job_rank)
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.7
    if distance == 2:
        return 0.4
    return 0.0


def filter_match_candidates_by_min_cosine_score(
    rows: list[dict[str, Any]],
    *,
    min_cosine_score: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter vector recall results by a minimum cosine score threshold."""
    if not 0.0 <= min_cosine_score <= 1.0:
        raise ValueError("min_cosine_score must be between 0.0 and 1.0")

    passed: list[dict[str, Any]] = []
    rejected_count = 0

    for row in rows:
        cosine_score = float(row.get("cosine_score") or 0.0)
        if cosine_score < min_cosine_score:
            rejected_count += 1
            continue
        passed.append(dict(row))

    return passed, {
        "enabled": True,
        "input_count": len(rows),
        "passed_count": len(passed),
        "rejected_count": rejected_count,
        "min_cosine_score": round(min_cosine_score, 6),
    }


def hard_filter_match_candidates(
    rows: list[dict[str, Any]],
    *,
    needs_sponsorship: bool,
    user_years: int | None,
    user_degree_rank: int,
    max_experience_gap: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply strict eligibility filters before reranking."""
    if max_experience_gap < 0:
        raise ValueError("max_experience_gap must be >= 0")

    passed: list[dict[str, Any]] = []
    rejected_by_reason = {
        "sponsorship": 0,
        "degree": 0,
        "experience": 0,
    }

    for row in rows:
        reasons: list[str] = []

        sponsorship_not_available = str(row.get("sponsorship_not_available") or "").strip().lower()
        if needs_sponsorship and sponsorship_not_available == "yes":
            reasons.append("sponsorship")

        jd_min_degree_rank = to_int(row.get("min_degree_rank"), default=-1)
        if (
            jd_min_degree_rank >= 0
            and user_degree_rank >= 0
            and jd_min_degree_rank > user_degree_rank
        ):
            reasons.append("degree")

        jd_years = to_optional_int(row.get("jd_experience_years"))
        if (
            jd_years is not None
            and user_years is not None
            and jd_years > user_years + max_experience_gap
        ):
            reasons.append("experience")

        if reasons:
            for reason in reasons:
                rejected_by_reason[reason] += 1
            continue

        item = dict(row)
        item["hard_filter"] = {
            "passed": True,
            "reasons": [],
        }
        passed.append(item)

    return passed, {
        "enabled": True,
        "input_count": len(rows),
        "passed_count": len(passed),
        "rejected_count": len(rows) - len(passed),
        "rejected_by_reason": rejected_by_reason,
        "config": {
            "needs_sponsorship": needs_sponsorship,
            "degree_filter_applied": user_degree_rank >= 0,
            "experience_filter_applied": user_years is not None,
            "max_experience_gap": max_experience_gap,
        },
    }


def rerank_match_candidates(
    rows: list[dict[str, Any]],
    *,
    user_years: int,
    user_degree_rank: int,
    user_skill_tokens: set[str] | None = None,
    user_domain: str = "unknown",
    user_seniority: str | None = None,
) -> list[dict[str, Any]]:
    """Apply weighted reranking over vector recall results."""
    user_skill_tokens = user_skill_tokens or set()
    results: list[dict[str, Any]] = []
    for row in rows:
        cosine = float(row.get("cosine_score") or 0.0)
        jd_years = row.get("jd_experience_years")
        jd_min_degree_rank = to_int(row.get("min_degree_rank"), default=-1)
        structured_jd = _parse_structured_jd_payload(row.get("structured_jd"))
        required_skills = structured_jd.get("required_skills", [])
        preferred_skills = structured_jd.get("preferred_skills", [])
        job_seniority = structured_jd.get("seniority_level")
        if not isinstance(job_seniority, str) or not job_seniority.strip():
            job_seniority = infer_seniority_level(
                str(row.get("title") or "").strip(), to_optional_int(jd_years)
            )

        if jd_years is None:
            experience_gap = 0
        else:
            experience_gap = max(0, int(jd_years) - user_years)
        experience_penalty = min(0.12, experience_gap * 0.04)

        education_gap = max(0, jd_min_degree_rank - user_degree_rank)
        education_penalty = min(0.08, education_gap * 0.08)
        skill_overlap_score = compute_skill_overlap_score(
            user_skill_tokens=user_skill_tokens,
            required_skills=required_skills if isinstance(required_skills, list) else [],
            preferred_skills=preferred_skills if isinstance(preferred_skills, list) else [],
        )
        domain_match_score = compute_domain_match_score(
            user_domain=user_domain,
            job_domain=str(row.get("job_domain_normalized") or "unknown"),
        )
        seniority_match_score = compute_seniority_match_score(
            user_seniority=user_seniority,
            job_seniority=job_seniority if isinstance(job_seniority, str) else None,
        )
        total_penalty = experience_penalty + education_penalty
        final_score = (
            0.70 * cosine
            + 0.15 * skill_overlap_score
            + 0.10 * domain_match_score
            + 0.05 * seniority_match_score
            - experience_penalty
            - education_penalty
        )

        item = dict(row)
        item.pop("structured_jd", None)
        item["cosine_score"] = round(cosine, 6)
        item["skill_overlap_score"] = round(skill_overlap_score, 6)
        item["domain_match_score"] = round(domain_match_score, 6)
        item["seniority_match_score"] = round(seniority_match_score, 6)
        item["experience_gap"] = experience_gap
        item["education_gap"] = education_gap
        item["penalties"] = {
            "experience_penalty": round(experience_penalty, 6),
            "education_penalty": round(education_penalty, 6),
            "total_penalty": round(total_penalty, 6),
        }
        item["score_breakdown"] = {
            "cosine_component": round(0.70 * cosine, 6),
            "skill_component": round(0.15 * skill_overlap_score, 6),
            "domain_component": round(0.10 * domain_match_score, 6),
            "seniority_component": round(0.05 * seniority_match_score, 6),
        }
        item["final_score"] = round(final_score, 6)
        results.append(item)

    results.sort(key=lambda item: item["final_score"], reverse=True)
    return results
