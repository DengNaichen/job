from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

from app.models import PlatformType, Source
from app.services.application.full_snapshot_sync import SourceSyncResult, SourceSyncStats


def _load_import_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "import_lever_jobs.py"
    spec = importlib.util.spec_from_file_location("import_lever_jobs_test_module", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise RuntimeError("Unable to load import_lever_jobs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False

    async def run_sync(self, fn):  # noqa: ANN001
        _ = fn
        return None


class _FakeEngine:
    def begin(self) -> _FakeConnection:
        return _FakeConnection()


def _make_source(identifier: str) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=PlatformType.LEVER,
        identifier=identifier,
    )


@pytest.mark.asyncio
async def test_run_filters_by_slug_and_prints_reconcile_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_import_module()
    monkeypatch.setattr(module, "engine", _FakeEngine())

    calls: list[dict[str, object]] = []
    source = _make_source("palantir")

    async def fake_load_lever_sources(*, slug, limit):  # noqa: ANN001
        calls.append({"slug": slug, "limit": limit})
        return [source]

    async def fake_sync_source(*, source, include_content, fetcher, mapper, dry_run):  # noqa: ANN001
        calls.append(
            {
                "identifier": source.identifier,
                "include_content": include_content,
                "dry_run": dry_run,
                "fetcher": type(fetcher).__name__,
                "mapper": type(mapper).__name__,
            }
        )
        return SourceSyncResult(
            source_id=str(source.id),
            source_key="lever:palantir",
            ok=True,
            stats=SourceSyncStats(
                fetched_count=5,
                mapped_count=5,
                unique_count=4,
                deduped_by_external_id=1,
                inserted_count=2,
                updated_count=2,
                closed_count=1,
            ),
        )

    monkeypatch.setattr(module, "_load_lever_sources", fake_load_lever_sources)
    monkeypatch.setattr(module, "_sync_source", fake_sync_source)

    args = argparse.Namespace(slug="palantir", limit=10, include_content=False, dry_run=True)
    await module.run(args)

    output = capsys.readouterr().out

    assert calls[0] == {"slug": "palantir", "limit": 10}
    assert calls[1] == {
        "identifier": "palantir",
        "include_content": False,
        "dry_run": True,
        "fetcher": "LeverFetcher",
        "mapper": "LeverMapper",
    }
    assert "target_sources=1" in output
    assert "unique=4" in output
    assert "deduped_by_external_id=1" in output
    assert "closed=1" in output
    assert "jobs_closed_total=1" in output


@pytest.mark.asyncio
async def test_run_reports_failed_sources(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_import_module()
    monkeypatch.setattr(module, "engine", _FakeEngine())

    sources = [_make_source("palantir"), _make_source("spotify")]

    async def fake_load_lever_sources(*, slug, limit):  # noqa: ANN001
        _ = (slug, limit)
        return sources

    async def fake_sync_source(*, source, include_content, fetcher, mapper, dry_run):  # noqa: ANN001
        _ = (include_content, fetcher, mapper, dry_run)
        if source.identifier == "spotify":
            return SourceSyncResult(
                source_id=str(source.id),
                source_key="lever:spotify",
                ok=False,
                stats=SourceSyncStats(failed_count=1),
                error="fetch boom",
            )
        return SourceSyncResult(
            source_id=str(source.id),
            source_key="lever:palantir",
            ok=True,
            stats=SourceSyncStats(
                fetched_count=2,
                mapped_count=2,
                unique_count=2,
                inserted_count=1,
                updated_count=1,
            ),
        )

    monkeypatch.setattr(module, "_load_lever_sources", fake_load_lever_sources)
    monkeypatch.setattr(module, "_sync_source", fake_sync_source)

    args = argparse.Namespace(slug=None, limit=None, include_content=True, dry_run=False)
    await module.run(args)

    output = capsys.readouterr().out

    assert "sources_success=1" in output
    assert "sources_failed=1" in output
    assert "failed_sources=spotify" in output
    assert "spotify (lever:spotify): FAILED: fetch boom" in output
