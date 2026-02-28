from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.models import PlatformType, Source
from app.services.stapply_greenhouse_audit import (
    GreenhouseCandidate,
    GreenhouseCandidateSummary,
    extract_greenhouse_identifier,
    filter_missing_greenhouse_candidates,
    load_greenhouse_candidates,
    read_candidates_csv,
    verify_greenhouse_candidate,
    write_candidates_csv,
)


def test_extract_greenhouse_identifier() -> None:
    assert extract_greenhouse_identifier("https://job-boards.greenhouse.io/airbnb") == "airbnb"
    assert extract_greenhouse_identifier("https://job-boards.greenhouse.io/airbnb/jobs") == "airbnb"
    assert extract_greenhouse_identifier("https://job-boards.greenhouse.io/") is None


def test_load_greenhouse_candidates_dedupes_identifier_and_name(tmp_path: Path) -> None:
    greenhouse_dir = tmp_path / "greenhouse"
    greenhouse_dir.mkdir()
    (greenhouse_dir / "greenhouse_companies.csv").write_text(
        "\n".join(
            [
                "name,url",
                "OpenAI,https://job-boards.greenhouse.io/openai",
                "OpenAI Duplicate,https://job-boards.greenhouse.io/openai",
                "Stripe,https://job-boards.greenhouse.io/stripe",
                "Stripe,https://job-boards.greenhouse.io/stripe-alt",
            ]
        ),
        encoding="utf-8",
    )

    candidates, summary = load_greenhouse_candidates(tmp_path)

    assert [(candidate.name, candidate.identifier) for candidate in candidates] == [
        ("OpenAI", "openai"),
        ("Stripe", "stripe"),
    ]
    assert summary.csv_rows == 4
    assert summary.valid_candidates == 2
    assert summary.duplicate_identifiers == 1
    assert summary.duplicate_names == 1


def test_filter_missing_greenhouse_candidates_respects_identifier_and_name_collisions() -> None:
    candidates = [
        GreenhouseCandidate(name="OpenAI", identifier="openai", url="https://job-boards.greenhouse.io/openai"),
        GreenhouseCandidate(name="Stripe", identifier="stripe-new", url="https://job-boards.greenhouse.io/stripe-new"),
        GreenhouseCandidate(name="Anthropic", identifier="anthropic", url="https://job-boards.greenhouse.io/anthropic"),
    ]
    existing_sources = [
        Source(
            name="OpenAI",
            name_normalized="openai",
            platform=PlatformType.GREENHOUSE,
            identifier="openai",
        ),
        Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        ),
    ]
    summary = GreenhouseCandidateSummary()

    missing = filter_missing_greenhouse_candidates(candidates, existing_sources, summary)

    assert [(candidate.name, candidate.identifier) for candidate in missing] == [("Anthropic", "anthropic")]
    assert summary.existing_in_db == 1
    assert summary.name_collisions == 1
    assert summary.missing_in_db == 1


@pytest.mark.asyncio
async def test_verify_greenhouse_candidate_success() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Engineer",
                        "absolute_url": "https://example.com/jobs/1",
                        "location": {"name": "Remote"},
                    }
                ]
            }

    class FakeClient:
        async def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            assert url.endswith("/openai/jobs")
            assert params == {"content": "false"}
            return FakeResponse()

    candidate = GreenhouseCandidate(
        name="OpenAI",
        identifier="openai",
        url="https://job-boards.greenhouse.io/openai",
    )

    result = await verify_greenhouse_candidate(candidate, client=FakeClient())

    assert result.name_ok is True
    assert result.identifier_ok is True
    assert result.fetch_ok is True
    assert result.map_ok is True
    assert result.job_count == 1
    assert result.eligible is True


@pytest.mark.asyncio
async def test_verify_greenhouse_candidate_records_http_status() -> None:
    class FakeResponse:
        status_code = 404

    class FakeClient:
        async def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            request = httpx.Request("GET", url, params=params)
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

    candidate = GreenhouseCandidate(
        name="12345678",
        identifier="12345678",
        url="https://job-boards.greenhouse.io/12345678",
    )

    result = await verify_greenhouse_candidate(candidate, client=FakeClient())

    assert result.name_ok is False
    assert result.fetch_ok is False
    assert result.eligible is False
    assert "name_is_numeric_only" in result.reasons
    assert "name_matches_numeric_identifier" in result.reasons
    assert "http_status:404" in result.reasons


def test_candidates_csv_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "report.csv"
    candidates = [
        GreenhouseCandidate(name="OpenAI", identifier="openai", url="https://job-boards.greenhouse.io/openai"),
        GreenhouseCandidate(name="Anthropic", identifier="anthropic", url="https://job-boards.greenhouse.io/anthropic"),
    ]

    write_candidates_csv(path, candidates)
    loaded = read_candidates_csv(path)

    assert loaded == candidates
