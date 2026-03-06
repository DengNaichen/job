"""Prompt templates and limits for JD parsing."""

MAX_JD_PARSE_CHARS = 6000
DEFAULT_BATCH_MAX_TOKENS = 8192
GEMINI_BATCH_MAX_TOKENS = 65536

EXTRACT_KEYWORDS_PROMPT = """Extract only the non-deterministic job fields as compact JSON.

Return EXACTLY:
{{
  "d": "job_domain_normalized",
  "s": ["required_skill_1", "required_skill_2"]
}}

Field meanings:
- d = role/function domain, not employer company sector
- s = required hard skills only

Allowed d values:
software_engineering, data_ai, product_program, design, sales_account_management,
marketing_growth, finance_treasury, operations, customer_support, hr_recruiting,
legal_compliance, cybersecurity, unknown

Rules:
1. Output valid JSON only.
2. Use at most 6 skills in s.
3. Keep skill phrases short, concrete, and deduplicated.
4. Do not output soft skills unless they are core screening criteria.
5. Do not repeat years, degree, sponsorship, or any fields outside d/s.

Job title:
{job_title}

Job description:
{job_description}"""

BATCH_EXTRACT_PROMPT = """Extract only the non-deterministic job fields for ALL jobs below.

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
1. Process ALL {count} jobs and include every exact i.
2. Use at most 6 skills in s for each job.
3. Keep skill phrases short, concrete, and deduplicated.
4. Do not output soft skills unless they are core screening criteria.
5. Do not output years, degree, sponsorship, or any fields outside i/d/s.

Jobs to process:
{jobs_text}"""
