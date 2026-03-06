"""Unit tests for LLM JD input builders."""

import pytest

from app.services.application.jd_parsing.llm_jd_input import build_batch_llm_jd_input


def test_build_batch_llm_jd_input_builds_alias_mapping_and_count() -> None:
    payload = build_batch_llm_jd_input(
        [
            {"job_id": "job-1", "title": "Backend Engineer", "description": "Python and SQL"},
            {"job_id": "job-2", "title": "Data Scientist", "description": "Machine Learning"},
        ],
        is_html=False,
    )

    assert payload.job_count == 2
    assert payload.input_aliases == ["j1", "j2"]
    assert payload.alias_to_job_id == {"j1": "job-1", "j2": "job-2"}
    assert "--- JOB ID: j1 ---" in payload.jobs_text
    assert "--- JOB ID: j2 ---" in payload.jobs_text


def test_build_batch_llm_jd_input_rejects_non_positive_max_jobs() -> None:
    jobs = [{"job_id": "job-1", "title": "Role", "description": "Text"}]

    with pytest.raises(ValueError, match="max_jobs must be > 0"):
        build_batch_llm_jd_input(jobs, is_html=False, max_jobs=0)


def test_build_batch_llm_jd_input_rejects_batch_over_max_jobs() -> None:
    jobs = [{"job_id": "job-1", "title": "Role", "description": "Text"}] * 2

    with pytest.raises(ValueError, match="Batch size exceeds max_jobs"):
        build_batch_llm_jd_input(jobs, is_html=False, max_jobs=1)
