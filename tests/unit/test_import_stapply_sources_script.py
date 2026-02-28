from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.models import PlatformType


def _load_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "import_stapply_sources.py"
    spec = importlib.util.spec_from_file_location("import_stapply_sources_test_module", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("Unable to load import_stapply_sources.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_first_path_segment_extracts_supported_identifiers() -> None:
    module = _load_module()

    assert module._first_path_segment("https://jobs.ashbyhq.com/openai") == "openai"
    assert module._first_path_segment("https://job-boards.greenhouse.io/airbnb") == "airbnb"
    assert module._first_path_segment("https://jobs.lever.co/stripe/job-id") == "stripe"
    assert (
        module._first_path_segment(
            "https://jobs.smartrecruiters.com/WSHGroup/744000091624446-bartender"
        )
        == "WSHGroup"
    )


def test_load_candidates_dedupes_by_platform_and_identifier(tmp_path: Path) -> None:
    module = _load_module()

    ashby_dir = tmp_path / "ashby"
    lever_dir = tmp_path / "lever"
    ashby_dir.mkdir()
    lever_dir.mkdir()

    (ashby_dir / "companies.csv").write_text(
        "\n".join(
            [
                "name,url",
                "OpenAI,https://jobs.ashbyhq.com/openai",
                "OpenAI Duplicate,https://jobs.ashbyhq.com/openai",
                "Anthropic,https://jobs.ashbyhq.com/anthropic",
            ]
        ),
        encoding="utf-8",
    )
    (lever_dir / "lever_companies.csv").write_text(
        "\n".join(
            [
                "name,url",
                "Stripe,https://jobs.lever.co/stripe",
                "Stripe Alt,https://jobs.lever.co/stripe/job-1",
                "1840&Company,https://jobs.lever.co/1840%26company",
                "1840&Company,https://jobs.lever.co/1840&company",
            ]
        ),
        encoding="utf-8",
    )

    candidates, summaries = module.load_candidates(tmp_path)

    assert len(candidates) == 4
    assert [
        (candidate.platform, candidate.identifier)
        for candidate in candidates
    ] == [
        (PlatformType.ASHBY, "openai"),
        (PlatformType.ASHBY, "anthropic"),
        (PlatformType.LEVER, "stripe"),
        (PlatformType.LEVER, "1840%26company"),
    ]
    assert summaries["ashby"].csv_rows == 3
    assert summaries["ashby"].valid_candidates == 2
    assert summaries["ashby"].csv_duplicates == 1
    assert summaries["ashby"].csv_name_duplicates == 0
    assert summaries["lever"].csv_rows == 4
    assert summaries["lever"].valid_candidates == 2
    assert summaries["lever"].csv_duplicates == 1
    assert summaries["lever"].csv_name_duplicates == 1


def test_validate_candidate_name_flags_numeric_placeholder_names() -> None:
    module = _load_module()
    candidate = module.SourceCandidate(
        platform=PlatformType.GREENHOUSE,
        name="103644278",
        identifier="103644278",
        url="https://job-boards.greenhouse.io/103644278",
    )

    reasons = module.validate_candidate_name(candidate)

    assert "name_is_numeric_only" in reasons
    assert "name_matches_numeric_identifier" in reasons


@pytest.mark.asyncio
async def test_verify_candidate_requires_live_fetch_and_sample_map(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    class FakeFetcher:
        async def fetch(self, identifier: str, include_content: bool = False):
            assert identifier == "openai"
            assert include_content is False
            return [{"id": "job-1"}]

    class FakeMapper:
        def map(self, raw_job: dict[str, str]):
            assert raw_job["id"] == "job-1"
            return {"ok": True}

    monkeypatch.setitem(module.FETCHER_FACTORIES, PlatformType.ASHBY, FakeFetcher)
    monkeypatch.setitem(module.MAPPER_FACTORIES, PlatformType.ASHBY, FakeMapper)

    candidate = module.SourceCandidate(
        platform=PlatformType.ASHBY,
        name="OpenAI",
        identifier="openai",
        url="https://jobs.ashbyhq.com/openai",
    )

    result = await module.verify_candidate(candidate)

    assert result.name_ok is True
    assert result.identifier_ok is True
    assert result.fetch_ok is True
    assert result.map_ok is True
    assert result.job_count == 1
    assert result.eligible_for_apply is True


@pytest.mark.asyncio
async def test_verify_candidate_rejects_invalid_name_without_apply_eligibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    class FakeFetcher:
        async def fetch(self, identifier: str, include_content: bool = False):
            return [{"id": "job-1"}]

    class FakeMapper:
        def map(self, raw_job: dict[str, str]):
            return {"ok": True}

    monkeypatch.setitem(module.FETCHER_FACTORIES, PlatformType.GREENHOUSE, FakeFetcher)
    monkeypatch.setitem(module.MAPPER_FACTORIES, PlatformType.GREENHOUSE, FakeMapper)

    candidate = module.SourceCandidate(
        platform=PlatformType.GREENHOUSE,
        name="123456789",
        identifier="123456789",
        url="https://job-boards.greenhouse.io/123456789",
    )

    result = await module.verify_candidate(candidate)

    assert result.fetch_ok is True
    assert result.map_ok is True
    assert result.name_ok is False
    assert result.eligible_for_apply is False
    assert "name_is_numeric_only" in result.reasons
