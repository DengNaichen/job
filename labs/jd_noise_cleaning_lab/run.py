#!/usr/bin/env python3
"""Heuristic lab for cleaning JD noise before embedding."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas.structured_jd import StructuredJD
from app.services.infra.text import html_to_text


SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "role_summary",
        re.compile(
            r"^(the role|role overview|position summary|job summary|about the role|about this role|about the team)$",
            re.I,
        ),
    ),
    (
        "responsibilities",
        re.compile(
            r"^(what you'll do|what you will do|responsibilities|your responsibilities|what you'll own|what you'll work on)$",
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
    ("benefits", re.compile(r"^(benefits|perks|why join us|what we offer|compensation)$", re.I)),
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
DROP_SECTIONS = {"company", "benefits", "work_auth", "legal", "apply"}

INLINE_DROP_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\bequal opportunity employer\b",
        r"\ball qualified applicants\b",
        r"\bcandidate privacy\b",
        r"\bprivacy notice\b",
        r"\bvisa sponsorship\b",
        r"\bwork authorization\b",
        r"\bsubmit your application\b",
        r"\bapply through\b",
        r"\bmedical, dental, and vision\b",
        r"\bremote-first culture\b",
        r"\bquarterly offsites\b",
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
    heading: str | None
    lines: list[str]
    decision: str
    score: int


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_line(text: str) -> str:
    text = text.strip()
    text = text.lstrip("-*• ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_key(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9#+./ ]+", " ", text)
    return " ".join(text.split())


def detect_section_heading(line: str) -> str | None:
    heading = line.strip()
    heading = re.sub(r"^[#*\-_ ]+", "", heading)
    heading = re.sub(r"[:*\-_ ]+$", "", heading)
    heading = heading.strip()
    for label, pattern in SECTION_PATTERNS:
        if pattern.fullmatch(heading):
            return label
    return None


def load_input(path: Path) -> tuple[str, str, StructuredJD]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    title = str(raw.get("title") or "").strip()
    description = str(raw.get("description") or "").strip()
    description_html = str(raw.get("description_html") or "").strip()
    structured = StructuredJD.model_validate(raw.get("structured_jd") or {})

    if description_html:
        description = html_to_text(description_html)
    return title, normalize_whitespace(description), structured


def split_into_sections(description: str) -> list[SectionBlock]:
    current_label = "body"
    current_heading: str | None = None
    current_lines: list[str] = []
    blocks: list[SectionBlock] = []

    def flush() -> None:
        if not current_lines and current_heading is None:
            return
        block_lines = [line for line in current_lines if line]
        label = current_label
        decision = "keep" if label in KEEP_SECTIONS else "drop"
        score = 0
        blocks.append(
            SectionBlock(
                label=label,
                heading=current_heading,
                lines=block_lines,
                decision=decision,
                score=score,
            )
        )

    for raw_line in description.splitlines():
        line = normalize_line(raw_line)
        if not line:
            continue
        section = detect_section_heading(line)
        if section is not None:
            flush()
            current_label = section
            current_heading = line.rstrip(":")
            current_lines = []
            continue
        current_lines.append(line)

    flush()
    return blocks


def score_line(line: str, structured: StructuredJD) -> int:
    lowered = normalize_key(line)
    score = 0

    if any(pattern.search(line) for pattern in INLINE_DROP_PATTERNS):
        return -10

    for skill in structured.required_skills[:12]:
        skill_key = normalize_key(skill)
        if skill_key and skill_key in lowered:
            score += 4

    for skill in structured.preferred_skills[:8]:
        skill_key = normalize_key(skill)
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


def dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = normalize_key(line)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def select_evidence(blocks: list[SectionBlock], structured: StructuredJD) -> dict[str, list[str]]:
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
            (line, score_line(line, structured))
            for line in block.lines
            if score_line(line, structured) >= 0
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
        selected[label] = dedupe_lines(lines)[: limits[label]]
    return selected


def build_embedding_text(
    *,
    title: str,
    structured: StructuredJD,
    evidence: dict[str, list[str]],
    max_chars: int,
) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"Title: {title}")
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


def summarize_blocks(blocks: list[SectionBlock], structured: StructuredJD) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for block in blocks:
        scored_lines = [(line, score_line(line, structured)) for line in block.lines]
        summary.append(
            {
                "label": block.label,
                "heading": block.heading,
                "decision": block.decision,
                "line_count": len(block.lines),
                "content_preview": [line for line, _ in scored_lines[:2]],
                "negative_preview": [line for line, score in scored_lines if score < 0][:2],
            }
        )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JD noise cleaning lab")
    parser.add_argument(
        "--input",
        default=str(Path(__file__).with_name("sample_job.json")),
        help="Input JSON payload",
    )
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    parser.add_argument("--max-chars", type=int, default=2200, help="Max output chars")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    title, description, structured = load_input(input_path)
    blocks = split_into_sections(description)
    evidence = select_evidence(blocks, structured)
    embedding_text = build_embedding_text(
        title=title,
        structured=structured,
        evidence=evidence,
        max_chars=max(200, args.max_chars),
    )
    report = {
        "input": str(input_path),
        "title": title,
        "original_chars": len(description),
        "section_summary": summarize_blocks(blocks, structured),
        "selected_evidence": evidence,
        "embedding_text_chars": len(embedding_text),
        "embedding_text": embedding_text,
        "structured_jd": structured.model_dump(mode="json"),
    }

    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output, encoding="utf-8")
        print(f"saved: {output_path}")
        return
    print(output)


if __name__ == "__main__":
    main()
