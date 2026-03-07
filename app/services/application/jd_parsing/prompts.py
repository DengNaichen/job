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
1. You MUST process ALL {job_count} jobs and include every exact i.
2. For each job, s MUST contain at most 12 items.
3. s MUST contain ONLY concrete hard skills and MUST be deduplicated.
4. Skill names MAY be normalized to standard wording (canonical phrasing), but you MUST NOT invent requirements not present in the JD.
5. Each skill in s MUST be a tool, technology, protocol, method, or certifiable task competency.
6. HARD FILTER (MUST): remove all soft skills and generic traits (communication, teamwork, leadership, problem solving, strategic thinking, stakeholder management, adaptability, ownership, detail oriented, fast paced, etc.).
7. HARD FILTER (MUST NOT): NEVER output role/domain/function labels as skills. Examples that MUST NOT appear in s: trust and safety, pharmaceutical sales, customer success, home health, software engineering, product management, operations, marketing.
8. HARD FILTER (MUST NOT): NEVER output business outcomes, KPIs, or scope-only phrases. Examples that MUST NOT appear in s: revenue growth, sales performance, budget management, people management, team leadership, networking, onboarding, performance metrics, growth strategy, account planning, category management, sales management, creator management, business planning, event management, product analysis, social media strategy, strategic partnerships.
9. Pattern ban (MUST): if a candidate skill is a generic noun phrase ending with words like management/leadership/growth/strategy/operations/success/performance/planning/relations/communications/partnerships and is not a concrete tool or certifiable method, you MUST DROP it (do not rewrite).
10. You MUST prefer specific, normalizable terms when possible (e.g., Kubernetes instead of k8s, Site Reliability Engineering instead of SRE, Power BI instead of powerbi, scikit-learn instead of scikit learn, TCP/IP instead of tcp ip).
11. If a job has fewer than 12 valid hard skills after filtering, you MUST return fewer than 12; if none remain, s MUST be [].
12. You MUST NOT output years, degree, sponsorship, responsibilities, or any fields outside i/d/s.
13. Final self-check (silent, REQUIRED before output): each item in s MUST pass ALL checks:
   - concrete hard skill/tool/protocol/method/certifiable competency
   - appears as a real requirement in the JD
   - not a domain label, not a soft skill, not a KPI/outcome phrase
   - specific enough to map to canonical taxonomy terms
   If any item fails any check, you MUST remove it.

Bad -> Good examples (skills list only):
- Bad: ["team leadership", "revenue growth", "trust and safety", "stakeholder management"]
  Good: ["Salesforce", "Sales forecasting", "Contract negotiation", "Pipeline management"]
- Bad: ["problem solving", "communication", "cross-functional collaboration", "software engineering"]
  Good: ["Kubernetes", "Terraform", "API design", "Distributed systems"]
- Bad: ["people management", "strategic thinking", "customer success", "budget management"]
  Good: ["Figma", "User research", "Usability testing", "Prototyping"]
- Bad: ["budget management", "sales performance", "growth strategy", "onboarding"]
  Good: ["SQL", "Tableau", "A/B testing", "Attribution modeling"]
- Bad: ["communication skills", "teamwork", "ownership", "problem solving"]
  Good: ["Python", "Pandas", "Airflow", "dbt"]

Jobs to process:
{jobs_text}"""


__all__ = [
    "MAX_JD_PARSE_CHARS",
    "DEFAULT_BATCH_MAX_TOKENS",
    "GEMINI_BATCH_MAX_TOKENS",
    "JD_PARSE_SYSTEM_PROMPT",
    "build_extract_prompt",
]
