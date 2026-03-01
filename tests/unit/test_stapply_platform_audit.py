from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.models import PlatformType, Source
from app.services import stapply_platform_audit as module


def test_smartrecruiters_identifier_prefers_company_segment() -> None:
    assert (
        module._smartrecruiters_identifier(
            "https://jobs.smartrecruiters.com/oneclick-ui/company/WSHGroup/publication/123"
        )
        == "WSHGroup"
    )
    assert (
        module._smartrecruiters_identifier(
            "https://jobs.smartrecruiters.com/WSHGroup/744000091624446-bartender"
        )
        == "WSHGroup"
    )


def test_load_candidates_dedupes_and_extracts_platform_identifier(tmp_path: Path) -> None:
    smart_dir = tmp_path / "smartrecruiters"
    smart_dir.mkdir()
    (smart_dir / "companies.csv").write_text(
        "\n".join(
            [
                "name,url",
                "WSH,https://jobs.smartrecruiters.com/WSHGroup/job-1",
                "WSH Duplicate,https://jobs.smartrecruiters.com/WSHGroup/job-2",
                "Oneclick Ui,https://jobs.smartrecruiters.com/oneclick-ui/company/WSHGroup/publication/1",
                "Visa,https://jobs.smartrecruiters.com/visa/job-1",
            ]
        ),
        encoding="utf-8",
    )

    candidates, summary = module.load_candidates(tmp_path, PlatformType.SMARTRECRUITERS)

    assert [(candidate.name, candidate.identifier) for candidate in candidates] == [
        ("WSH", "WSHGroup"),
        ("Visa", "visa"),
    ]
    assert summary.csv_rows == 4
    assert summary.valid_candidates == 2
    assert summary.duplicate_identifiers == 2
    assert summary.duplicate_names == 0


def test_filter_missing_candidates_respects_identifier_and_name_collisions() -> None:
    candidates = [
        module.SourceCandidate(
            platform=PlatformType.LEVER,
            name="OpenAI",
            identifier="openai",
            url="https://jobs.lever.co/openai",
        ),
        module.SourceCandidate(
            platform=PlatformType.LEVER,
            name="Stripe",
            identifier="stripe-new",
            url="https://jobs.lever.co/stripe-new",
        ),
        module.SourceCandidate(
            platform=PlatformType.LEVER,
            name="Anthropic",
            identifier="anthropic",
            url="https://jobs.lever.co/anthropic",
        ),
    ]
    existing_sources = [
        Source(
            name="OpenAI",
            name_normalized="openai",
            platform=PlatformType.LEVER,
            identifier="openai",
        ),
        Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.LEVER,
            identifier="stripe",
        ),
    ]
    summary = module.CandidateSummary()

    missing = module.filter_missing_candidates(candidates, existing_sources, summary)

    assert [(candidate.name, candidate.identifier) for candidate in missing] == [
        ("Anthropic", "anthropic")
    ]
    assert summary.existing_in_db == 1
    assert summary.name_collisions == 1
    assert summary.missing_in_db == 1


@pytest.mark.asyncio
async def test_verify_candidate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeFetcher:
        async def fetch(self, slug: str, include_content: bool = False):
            assert slug == "openai"
            assert include_content is False
            return [{"id": "job-1", "text": "Engineer", "applyUrl": "https://example.com/jobs/1"}]

    class FakeMapper:
        def map(self, raw_job: dict[str, str]):
            assert raw_job["id"] == "job-1"
            return {"ok": True}

    monkeypatch.setitem(
        module.PLATFORM_AUDIT_CONFIGS,
        PlatformType.LEVER,
        module.PlatformAuditConfig(
            platform=PlatformType.LEVER,
            relative_csv_path="lever/lever_companies.csv",
            identifier_from_url=module._first_path_segment,
            fetcher_factory=FakeFetcher,
            mapper_factory=FakeMapper,
            include_content=False,
            default_verify_concurrency=2,
        ),
    )

    candidate = module.SourceCandidate(
        platform=PlatformType.LEVER,
        name="OpenAI",
        identifier="openai",
        url="https://jobs.lever.co/openai",
    )
    result = await module.verify_candidate(candidate)

    assert result.name_ok is True
    assert result.identifier_ok is True
    assert result.fetch_ok is True
    assert result.map_ok is True
    assert result.job_count == 1
    assert result.eligible is True


@pytest.mark.asyncio
async def test_verify_candidate_records_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeFetcher:
        async def fetch(self, slug: str, include_content: bool = False):
            request = httpx.Request("GET", f"https://example.com/{slug}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("missing", request=request, response=response)

    class FakeMapper:
        def map(self, raw_job: dict[str, str]):
            return {"ok": True}

    monkeypatch.setitem(
        module.PLATFORM_AUDIT_CONFIGS,
        PlatformType.ASHBY,
        module.PlatformAuditConfig(
            platform=PlatformType.ASHBY,
            relative_csv_path="ashby/companies.csv",
            identifier_from_url=module._first_path_segment,
            fetcher_factory=FakeFetcher,
            mapper_factory=FakeMapper,
            include_content=False,
            default_verify_concurrency=2,
        ),
    )

    candidate = module.SourceCandidate(
        platform=PlatformType.ASHBY,
        name="123456",
        identifier="123456",
        url="https://jobs.ashbyhq.com/123456",
    )
    result = await module.verify_candidate(candidate)

    assert result.name_ok is False
    assert result.fetch_ok is False
    assert result.eligible is False
    assert "name_is_numeric_only" in result.reasons
    assert "name_matches_numeric_identifier" in result.reasons
    assert "http_status:404" in result.reasons


def test_candidate_csv_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "candidates.csv"
    candidates = [
        module.SourceCandidate(
            platform=PlatformType.ASHBY,
            name="OpenAI",
            identifier="openai",
            url="https://jobs.ashbyhq.com/openai",
        ),
        module.SourceCandidate(
            platform=PlatformType.SMARTRECRUITERS,
            name="Visa",
            identifier="visa",
            url="https://jobs.smartrecruiters.com/visa/job-1",
        ),
    ]

    module.write_candidates_csv(path, candidates)
    loaded = module.read_candidates_csv(path)

    assert loaded == candidates
