"""Pydantic schema for LLM-extracted job description structure."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STRUCTURED_JD_SCHEMA_VERSION = 3

SponsorshipAvailability = Literal["yes", "no", "unknown"]
DegreeLevel = Literal["none", "associate", "bachelor", "master", "doctorate", "unknown"]
JobDomainNormalized = Literal[
    "software_engineering",
    "data_ai",
    "product_program",
    "design",
    "sales_account_management",
    "marketing_growth",
    "finance_treasury",
    "operations",
    "customer_support",
    "hr_recruiting",
    "legal_compliance",
    "cybersecurity",
    "unknown",
]

DEGREE_LEVEL_RANK: dict[str, int] = {
    "none": 0,
    "associate": 1,
    "bachelor": 2,
    "master": 3,
    "doctorate": 4,
    "unknown": -1,
}

_JOB_DOMAIN_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "cybersecurity",
        (
            "cybersecurity",
            "security",
            "threat",
            "malware",
            "fraud",
            "siem",
            "soc",
            "trust and safety",
        ),
    ),
    (
        "legal_compliance",
        ("legal", "compliance", "privacy", "regulatory", "contracts", "sanctions", "aml", "policy"),
    ),
    (
        "finance_treasury",
        (
            "finance",
            "financial",
            "treasury",
            "banking",
            "payments",
            "accounting",
            "fp&a",
            "audit",
            "tax",
            "controller",
        ),
    ),
    (
        "hr_recruiting",
        ("recruit", "recruiting", "talent", "people ops", "human resources", "hr ", "sourcer"),
    ),
    (
        "customer_support",
        (
            "customer support",
            "customer service",
            "customer success",
            "service recovery",
            "call center",
            "support quality",
            "support",
        ),
    ),
    (
        "marketing_growth",
        (
            "marketing",
            "growth",
            "brand",
            "content",
            "communications",
            "crm",
            "seo",
            "pr",
            "demand generation",
        ),
    ),
    (
        "sales_account_management",
        (
            "sales",
            "account executive",
            "account manager",
            "business development",
            "partnership",
            "partnerships",
            "acquisition",
            "revenue",
        ),
    ),
    (
        "product_program",
        (
            "product manager",
            "product management",
            "technical product manager",
            "program manager",
            "project manager",
            "tpm",
        ),
    ),
    (
        "data_ai",
        (
            "data scientist",
            "data science",
            "data analyst",
            "analytics",
            "machine learning",
            "ml ",
            " llm",
            "artificial intelligence",
            "business intelligence",
            "bi ",
        ),
    ),
    ("design", ("design", "designer", "ux", "ui", "product design", "visual design")),
    (
        "operations",
        (
            "operations",
            "strategy",
            "business analyst",
            "workforce",
            "wfm",
            "planning",
            "procurement",
            "logistics",
            "supply chain",
        ),
    ),
    (
        "software_engineering",
        (
            "software",
            "engineering",
            "engineer",
            "developer",
            "backend",
            "frontend",
            "full stack",
            "devops",
            "sre",
            "platform",
        ),
    ),
]

_LEGACY_INDUSTRY_TO_JOB_DOMAIN: dict[str, JobDomainNormalized] = {
    "software_internet": "software_engineering",
    "fintech": "finance_treasury",
    "healthcare_biotech": "operations",
    "ecommerce_retail": "operations",
    "education": "operations",
    "media_entertainment": "marketing_growth",
    "consulting_professional_services": "operations",
    "manufacturing_hardware": "operations",
    "logistics_supply_chain": "operations",
    "energy_climate": "operations",
    "government_public_sector": "operations",
    "nonprofit": "operations",
}


def normalize_sponsorship(value: object) -> SponsorshipAvailability:
    """Normalize sponsorship flag to yes/no/unknown."""
    if value is None:
        return "unknown"

    text = str(value).strip().lower()
    if not text:
        return "unknown"

    if text in {"yes", "y", "true", "1"}:
        return "yes"
    if text in {"no", "n", "false", "0"}:
        return "no"
    if text == "unknown":
        return "unknown"

    deny_markers = (
        "no sponsorship",
        "not sponsor",
        "unable to sponsor",
        "unable to provide visa sponsorship",
        "without sponsorship",
        "sponsorship not available",
        "cannot sponsor",
        "visa sponsorship unavailable",
        "visa sponsorship is not provided",
        "sponsorship is not provided",
    )
    allow_markers = (
        "sponsorship available",
        "can sponsor",
        "visa sponsorship provided",
        "will sponsor",
    )
    if any(marker in text for marker in deny_markers):
        return "yes"
    if any(marker in text for marker in allow_markers):
        return "no"
    return "unknown"


def normalize_job_domain_name(value: object) -> JobDomainNormalized:
    """Normalize role/function domain to fixed categories."""
    if value is None:
        return "unknown"

    text = str(value).strip().lower()
    if not text:
        return "unknown"

    known_values = {
        "software_engineering",
        "data_ai",
        "product_program",
        "design",
        "sales_account_management",
        "marketing_growth",
        "finance_treasury",
        "operations",
        "customer_support",
        "hr_recruiting",
        "legal_compliance",
        "cybersecurity",
        "unknown",
    }
    if text in known_values:
        return text  # type: ignore[return-value]

    if text in _LEGACY_INDUSTRY_TO_JOB_DOMAIN:
        return _LEGACY_INDUSTRY_TO_JOB_DOMAIN[text]

    for normalized, markers in _JOB_DOMAIN_KEYWORDS:
        if any(marker in text for marker in markers):
            return normalized  # type: ignore[return-value]
    return "unknown"


def normalize_degree_level(value: object) -> DegreeLevel:
    """Normalize degree level values."""
    if value is None:
        return "unknown"

    text = str(value).strip().lower()
    if not text:
        return "unknown"

    if text in DEGREE_LEVEL_RANK:
        return text  # type: ignore[return-value]

    if any(
        token in text
        for token in ("phd", "ph.d", "doctorate", "doctoral", "md", "m.d", "juris doctor", "jd ")
    ):
        return "doctorate"
    if any(token in text for token in ("master", "m.s", "ms ", "msc", "m.sc", "mba", "ma ", "m.a")):
        return "master"
    if any(token in text for token in ("bachelor", "b.s", "bs ", "b.a", "ba ", "undergraduate")):
        return "bachelor"
    if any(token in text for token in ("associate", "community college")):
        return "associate"
    if any(token in text for token in ("not required", "no degree", "none", "n/a")):
        return "none"

    return "unknown"


def degree_level_to_rank(level: str) -> int:
    """Map degree level to sortable rank."""
    return DEGREE_LEVEL_RANK.get(level, -1)


def build_structured_jd_storage_payload(
    payload: StructuredJD | dict[str, object],
) -> dict[str, object]:
    """Build a compact structured_jd payload for JSONB storage.

    Canonical filter/sort fields live in typed Job columns and should not be
    duplicated in the JSON payload.
    """
    if isinstance(payload, StructuredJD):
        parsed = payload
    else:
        data = dict(payload)
        data.pop("job_id", None)
        parsed = StructuredJD.model_validate(data)

    result: dict[str, object] = {
        "required_skills": parsed.required_skills,
        "preferred_skills": parsed.preferred_skills,
        "experience_requirements": parsed.experience_requirements,
        "education_requirements": parsed.education_requirements,
        "experience_years": parsed.experience_years,
        "seniority_level": parsed.seniority_level,
        "job_domain_raw": parsed.job_domain_raw,
    }
    compact: dict[str, object] = {}
    for key, value in result.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        compact[key] = value
    return compact


def build_structured_jd_projection(payload: StructuredJD | dict[str, object]) -> dict[str, object]:
    """Build typed Job columns from structured_jd payload."""
    if isinstance(payload, StructuredJD):
        parsed = payload
    else:
        data = dict(payload)
        data.pop("job_id", None)
        parsed = StructuredJD.model_validate(data)

    min_degree_level = parsed.min_degree_level
    return {
        "sponsorship_not_available": parsed.sponsorship_not_available,
        "job_domain_raw": parsed.job_domain_raw,
        "job_domain_normalized": parsed.job_domain_normalized,
        "min_degree_level": min_degree_level,
        "min_degree_rank": degree_level_to_rank(min_degree_level),
        "structured_jd_version": STRUCTURED_JD_SCHEMA_VERSION,
    }


class StructuredJD(BaseModel):
    """LLM extracted structured job fields."""

    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_requirements: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    experience_years: int | None = Field(default=None)
    seniority_level: str | None = Field(default=None)
    sponsorship_not_available: SponsorshipAvailability = Field(default="unknown")
    job_domain_raw: str | None = Field(default=None)
    job_domain_normalized: JobDomainNormalized = Field(default="unknown")
    min_degree_level: DegreeLevel = Field(default="unknown")

    @model_validator(mode="before")
    # TODO: clean this later
    @classmethod
    def normalize_legacy_field_names(cls, value: object) -> object:
        """Accept legacy industry_* keys during the transition to job_domain_*."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "job_domain_raw" not in data and "industry_raw" in data:
            data["job_domain_raw"] = data.pop("industry_raw")
        if "job_domain_normalized" not in data and "industry_normalized" in data:
            data["job_domain_normalized"] = data.pop("industry_normalized")

        # Legacy keys retained in historical payloads; ignored in current schema.
        data.pop("key_responsibilities", None)
        data.pop("keywords", None)
        return data

    @field_validator(
        "required_skills",
        "preferred_skills",
        "experience_requirements",
        "education_requirements",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> list[str]:
        """Normalize list-like fields into list[str]."""
        if value is None:
            return []
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
        else:
            text = str(value).strip()
            normalized = [text] if text else []

        seen: set[str] = set()
        deduped: list[str] = []
        for item in normalized:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(item)
        return deduped

    @field_validator("experience_years", mode="before")
    @classmethod
    def normalize_experience_years(cls, value: object) -> int | None:
        """Normalize experience_years to int or None."""
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(float(stripped))
            except ValueError:
                return None
        if isinstance(value, (int, float)):
            return int(value)
        return None

    @field_validator("sponsorship_not_available", mode="before")
    @classmethod
    def normalize_sponsorship_not_available(cls, value: object) -> SponsorshipAvailability:
        """Normalize sponsorship value."""
        return normalize_sponsorship(value)

    @field_validator("job_domain_raw", mode="before")
    @classmethod
    def normalize_job_domain_raw(cls, value: object) -> str | None:
        """Normalize raw job domain text."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "unknown":
            return None
        return text or None

    @field_validator("job_domain_normalized", mode="before")
    @classmethod
    def normalize_job_domain_normalized(cls, value: object) -> JobDomainNormalized:
        """Normalize role/function domain category."""
        return normalize_job_domain_name(value)

    @field_validator("min_degree_level", mode="before")
    @classmethod
    def normalize_min_degree_level(cls, value: object) -> DegreeLevel:
        """Normalize minimum degree level."""
        return normalize_degree_level(value)

    @model_validator(mode="after")
    def derive_fields(self) -> StructuredJD:
        """Derive normalized fields from raw text when possible."""
        if self.job_domain_normalized == "unknown" and self.job_domain_raw:
            self.job_domain_normalized = normalize_job_domain_name(self.job_domain_raw)
        if self.min_degree_level == "unknown" and self.education_requirements:
            joined = " ".join(self.education_requirements)
            self.min_degree_level = normalize_degree_level(joined)
        return self


class BatchStructuredJDItem(StructuredJD):
    """Single batch parse item with job_id for mapping."""

    job_id: str


class BatchStructuredJD(BaseModel):
    """Batch parse response."""

    model_config = ConfigDict(extra="forbid")

    jobs: list[BatchStructuredJDItem] = Field(default_factory=list)


class CompactStructuredJD(BaseModel):
    """Low-cost single JD response using short keys."""

    model_config = ConfigDict(extra="forbid")

    d: JobDomainNormalized = Field(default="unknown")
    s: list[str] = Field(default_factory=list)

    @field_validator("s", mode="before")
    @classmethod
    def normalize_skills(cls, value: object) -> list[str]:
        """Normalize compact skill list."""
        if value is None:
            return []
        if isinstance(value, list):
            skills = [str(item).strip() for item in value if str(item).strip()]
        else:
            text = str(value).strip()
            skills = [text] if text else []

        deduped: list[str] = []
        seen: set[str] = set()
        for item in skills:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(item)
        return deduped[:6]


class CompactBatchStructuredJDItem(CompactStructuredJD):
    """Low-cost batch parse item."""

    i: str


class CompactBatchStructuredJD(BaseModel):
    """Low-cost batch parse response."""

    model_config = ConfigDict(extra="forbid")

    jobs: list[CompactBatchStructuredJDItem] = Field(default_factory=list)
