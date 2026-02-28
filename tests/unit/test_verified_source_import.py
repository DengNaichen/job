from __future__ import annotations

from app.models import PlatformType
from app.services.verified_source_import import (
    EligibleSourceCandidate,
    resolve_overlap_candidates,
)


def test_resolve_overlap_candidates_applies_manual_winner_and_preserves_non_overlap() -> None:
    candidates = [
        EligibleSourceCandidate(
            platform=PlatformType.ASHBY,
            name="Aleph",
            identifier="aleph",
            url="https://jobs.ashbyhq.com/aleph",
            job_count=10,
        ),
        EligibleSourceCandidate(
            platform=PlatformType.LEVER,
            name="Aleph",
            identifier="aleph",
            url="https://jobs.lever.co/aleph",
            job_count=82,
        ),
        EligibleSourceCandidate(
            platform=PlatformType.GREENHOUSE,
            name="OpenAI",
            identifier="openai",
            url="https://job-boards.greenhouse.io/openai",
            job_count=5,
        ),
    ]

    selected, overlap_rows = resolve_overlap_candidates(candidates)

    assert [(candidate.platform, candidate.identifier) for candidate in selected] == [
        (PlatformType.GREENHOUSE, "openai"),
        (PlatformType.LEVER, "aleph"),
    ]
    assert len(overlap_rows) == 2
    assert [row["selected"] for row in overlap_rows] == ["False", "True"]
