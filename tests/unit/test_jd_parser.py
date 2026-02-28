"""Unit tests for JD parser low-cost compact parsing."""

import pytest

from app.services.jd_parser import parse_jd, parse_jd_batch


@pytest.mark.asyncio
async def test_parse_jd_defaults_missing_new_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete_json(**kwargs):  # noqa: ANN003
        return {
            "d": "software_engineering",
            "s": ["Python", "SQL"],
        }

    monkeypatch.setattr("app.services.jd_parser.complete_json", fake_complete_json)

    parsed = await parse_jd("Backend engineer with Python", title="Backend Engineer")

    assert parsed.required_skills == ["Python", "SQL"]
    assert parsed.experience_years is None
    assert parsed.sponsorship_not_available == "unknown"
    assert parsed.job_domain_normalized == "software_engineering"
    assert parsed.min_degree_level == "unknown"


@pytest.mark.asyncio
async def test_parse_jd_normalizes_new_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete_json(**kwargs):  # noqa: ANN003
        return {
            "d": "unknown",
            "s": ["malware analysis", "Python"],
        }

    monkeypatch.setattr("app.services.jd_parser.complete_json", fake_complete_json)

    parsed = await parse_jd(
        """
        Threat hunting role.
        Bachelor's in Computer Science or related degree.
        Experience 2-5 years in cybersecurity research.
        """,
        title="Threat Researcher",
    )

    assert parsed.sponsorship_not_available == "unknown"
    assert parsed.job_domain_normalized == "cybersecurity"
    assert parsed.min_degree_level == "bachelor"
    assert parsed.experience_years == 2
    assert parsed.required_skills == ["malware analysis", "Python"]


@pytest.mark.asyncio
async def test_parse_jd_batch_merges_compact_llm_output_with_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete_json(**kwargs):  # noqa: ANN003
        return {
            "jobs": [
                {"i": "job-1", "d": "finance_treasury", "s": ["banking", "swift"]},
                {"i": "job-2", "d": "software_engineering", "s": ["python", "sql"]},
            ]
        }

    monkeypatch.setattr("app.services.jd_parser.complete_json", fake_complete_json)

    parsed = await parse_jd_batch(
        [
            {
                "job_id": "job-1",
                "title": "Treasury Manager",
                "description": "Master's degree required. 8-12 years of relevant experience. No sponsorship available.",
            },
            {
                "job_id": "job-2",
                "title": "Backend Engineer",
                "description": "Strong Python and SQL skills. 3+ years of experience.",
            },
        ]
    )

    assert len(parsed.jobs) == 2
    assert parsed.jobs[0].job_domain_normalized == "finance_treasury"
    assert parsed.jobs[0].sponsorship_not_available == "yes"
    assert parsed.jobs[0].min_degree_level == "master"
    assert parsed.jobs[0].experience_years == 8
    assert parsed.jobs[1].job_domain_normalized == "software_engineering"
    assert parsed.jobs[1].experience_years == 3
