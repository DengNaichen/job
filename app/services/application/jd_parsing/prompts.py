"""Prompt templates and limits for JD parsing."""

MAX_JD_PARSE_CHARS = 6000
DEFAULT_BATCH_MAX_TOKENS = 8192
GEMINI_BATCH_MAX_TOKENS = 65536

JD_PARSE_SYSTEM_PROMPT = "You are an expert job description analyzer. Process all jobs accurately."


def build_extract_prompt(*, job_count: int, jobs_text: str) -> str:
    """Build extraction prompt for one or many jobs using a single contract."""
    if job_count <= 0:
        raise ValueError("job_count must be > 0")

    return f"""Extract only the non-deterministic job fields for ALL jobs below.

Output EXACTLY:
{{
  "jobs": [
    {{"i": "job_id", "d": "job_domain_normalized", "s": ["required_skill_1"]}}
  ]
}}

Field meanings:
- i = exact job_id from input
- d = role/function domain, not employer company sector
- s = required hard skills only

Allowed d values:
software_engineering, data_ai, product_program, design, sales_account_management,
marketing_growth, finance_treasury, operations, customer_support, hr_recruiting,
legal_compliance, cybersecurity, unknown

Rules:
1. Process ALL {job_count} jobs and include every exact i.
2. Use at most 6 skills in s for each job.
3. Keep skill phrases short, concrete, and deduplicated.
4. Do not output soft skills unless they are core screening criteria.
5. Do not output years, degree, sponsorship, or any fields outside i/d/s.

Jobs to process:
{jobs_text}"""


__all__ = [
    "MAX_JD_PARSE_CHARS",
    "DEFAULT_BATCH_MAX_TOKENS",
    "GEMINI_BATCH_MAX_TOKENS",
    "JD_PARSE_SYSTEM_PROMPT",
    "build_extract_prompt",
]
