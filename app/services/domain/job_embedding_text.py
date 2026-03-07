"""Job-side embedding text builder."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.structured_jd import StructuredJD

DEFAULT_MAX_JOB_EMBEDDING_CHARS = 2200

SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "role_summary",
        re.compile(
            r"^(the role|role overview|position summary|job summary|about the role|about this role|about the team|the opportunity)$",
            re.I,
        ),
    ),
    (
        "responsibilities",
        re.compile(
            r"^(what you'll do|what you will do|responsibilities|your responsibilities|what you'll own|what you'll work on|key responsibilities)$",
            re.I,
        ),
    ),
    (
        "requirements",
        re.compile(
            r"^(requirements|qualifications|minimum qualifications|basic qualifications|must have|must-have|what you bring|about you|who you are|what we're looking for|what we are looking for)$",
            re.I,
        ),
    ),
    (
        "preferred",
        re.compile(
            r"^(nice to have|preferred qualifications|bonus points|preferred|good to have)$",
            re.I,
        ),
    ),
    (
        "company",
        re.compile(
            r"^(about(?: .+)?|about us|about the company|who we are|company overview|company description)$",
            re.I,
        ),
    ),
    ("benefits", re.compile(r"^(benefits|perks|why join us|what we offer|compensation|our benefits)$", re.I)),
    (
        "work_auth",
        re.compile(r"^(work authorization|visa|sponsorship|employment eligibility)$", re.I),
    ),
    ("legal", re.compile(r"^(eeo statement|equal opportunity|privacy notice|legal notice)$", re.I)),
    (
        "apply",
        re.compile(r"^(how to apply|application process|interview process|next steps)$", re.I),
    ),
]

KEEP_SECTIONS = {"role_summary", "responsibilities", "requirements", "preferred", "body"}

INLINE_DROP_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\bequal opportunity employer\b",
        r"\bequal opportunities employer\b",
        r"\ball qualified applicants\b",
        r"\bcandidate privacy\b",
        r"\bprivacy notice\b",
        r"\bvisa sponsorship\b",
        r"\bwork authorization\b",
        r"\bsubmit your application\b",
        r"\bapply through\b",
        r"\bmedical, dental, and vision\b",
        r"\bprivate health insurance\b",
        r"\bdisability insurance\b",
        r"\bpaid sick leave\b",
        r"\bvacation days\b",
        r"\bparental leave\b",
        r"\b401\(k\)\b",
        r"\bcommuter benefit\b",
        r"\bquarterly offsites\b",
        r"\bcompany social events\b",
        r"\binclusive workplace\b",
    )
]

DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "cybersecurity": ("fraud", "risk", "security", "abuse", "trust", "threat"),
    "software_engineering": ("backend", "platform", "api", "distributed systems", "service"),
    "data_ai": ("machine learning", "model", "analytics", "feature", "inference"),
}


@dataclass(frozen=True)
class SectionBlock:
    label: str
    lines: list[str]
    decision: str


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_line(text: str) -> str:
    text = text.strip()
    text = text.lstrip("-*• ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_key(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9#+./ ]+", " ", text)
    return " ".join(text.split())


def _coerce_structured_jd(payload: object) -> StructuredJD:
    if isinstance(payload, StructuredJD):
        return payload
    try:
        return StructuredJD.model_validate(payload or {})
    except ValidationError:
        return StructuredJD()


def _detect_section_heading(line: str) -> str | None:
    heading = line.strip()
    heading = re.sub(r"^[#*\-_ ]+", "", heading)
    heading = re.sub(r"[:*\-_ ]+$", "", heading)
    heading = heading.strip()
    for label, pattern in SECTION_PATTERNS:
        if pattern.fullmatch(heading):
            return label
    return None


def _split_into_sections(description: str) -> list[SectionBlock]:
    current_label = "body"
    current_lines: list[str] = []
    blocks: list[SectionBlock] = []

    def flush() -> None:
        if not current_lines:
            return
        label = current_label
        blocks.append(
            SectionBlock(
                label=label,
                lines=[line for line in current_lines if line],
                decision="keep" if label in KEEP_SECTIONS else "drop",
            )
        )

    for raw_line in description.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue
        section = _detect_section_heading(line)
        if section is not None:
            flush()
            current_label = section
            current_lines = []
            continue
        current_lines.append(line)

    flush()
    return blocks


def _score_line(line: str, structured: StructuredJD) -> int:
    lowered = _normalize_key(line)
    score = 0

    if any(pattern.search(line) for pattern in INLINE_DROP_PATTERNS):
        return -10

    for skill in structured.required_skills[:12]:
        skill_key = _normalize_key(skill)
        if skill_key and skill_key in lowered:
            score += 4

    for skill in structured.preferred_skills[:8]:
        skill_key = _normalize_key(skill)
        if skill_key and skill_key in lowered:
            score += 2

    domain = structured.job_domain_normalized
    if domain != "unknown":
        for hint in DOMAIN_HINTS.get(domain, ()):
            if hint in lowered:
                score += 2

    if any(token in lowered for token in ("build", "design", "improve", "partner", "mentor")):
        score += 1
    if any(token in lowered for token in ("experience", "strong", "ability", "familiarity")):
        score += 1
    return score


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = _normalize_key(line)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def _select_evidence(blocks: list[SectionBlock], structured: StructuredJD) -> dict[str, list[str]]:
    selected: dict[str, list[str]] = {
        "role_summary": [],
        "responsibilities": [],
        "requirements": [],
        "preferred": [],
        "body": [],
    }
    limits = {
        "role_summary": 2,
        "responsibilities": 5,
        "requirements": 5,
        "preferred": 2,
        "body": 3,
    }

    for block in blocks:
        if block.decision != "keep":
            continue
        scored = [
            (line, _score_line(line, structured))
            for line in block.lines
            if _score_line(line, structured) >= 0
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        bucket = selected.get(block.label)
        if bucket is None:
            continue
        for line, _ in scored:
            bucket.append(line)
            if len(bucket) >= limits[block.label]:
                break

    for label, lines in selected.items():
        selected[label] = _dedupe_lines(lines)[: limits[label]]
    return selected


def build_job_embedding_text(
    *,
    title: str,
    description: str,
    structured_jd: StructuredJD | dict[str, object] | None = None,
    max_chars: int = DEFAULT_MAX_JOB_EMBEDDING_CHARS,
) -> str:
    structured = _coerce_structured_jd(structured_jd)
    normalized_description = _normalize_whitespace(description)
    blocks = _split_into_sections(normalized_description)
    evidence = _select_evidence(blocks, structured)

    parts: list[str] = []
    if title:
        parts.append(f"Title: {title.strip()}")
    if structured.job_domain_normalized != "unknown":
        parts.append(f"Domain: {structured.job_domain_normalized.replace('_', ' ')}")
    if structured.seniority_level:
        parts.append(f"Seniority: {structured.seniority_level}")
    if structured.required_skills:
        parts.append("Required skills: " + ", ".join(structured.required_skills[:10]))
    if evidence["role_summary"]:
        parts.append("Role summary:\n- " + "\n- ".join(evidence["role_summary"]))
    if evidence["responsibilities"]:
        parts.append("Core responsibilities:\n- " + "\n- ".join(evidence["responsibilities"]))
    if evidence["requirements"]:
        parts.append("Must-have evidence:\n- " + "\n- ".join(evidence["requirements"]))
    if evidence["preferred"]:
        parts.append("Optional context:\n- " + "\n- ".join(evidence["preferred"]))
    if evidence["body"]:
        parts.append("Additional role context:\n- " + "\n- ".join(evidence["body"]))

    text = "\n\n".join(parts).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


__all__ = ["DEFAULT_MAX_JOB_EMBEDDING_CHARS", "build_job_embedding_text"]
