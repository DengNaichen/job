from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

from app.models import PlatformType, Source
from app.services.full_snapshot_sync import SourceSyncResult, SourceSyncStats


def _load_import_module(filename: str, module_name: str):
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"Unable to load {filename}")
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


def _make_source(identifier: str, platform: PlatformType) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=platform,
        identifier=identifier,
    )


@pytest.mark.asyncio
async def test_import_apple_run_filters_by_slug_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_import_module("import_apple_jobs.py", "import_apple_jobs_test_module")
    monkeypatch.setattr(module, "engine", _FakeEngine())

    calls: list[dict[str, object]] = []
    source = _make_source("apple", PlatformType.APPLE)

    async def fake_load_apple_sources(*, slug, limit):  # noqa: ANN001
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
            source_key="apple:apple",
            ok=True,
            stats=SourceSyncStats(
                fetched_count=3, mapped_count=3, unique_count=3, inserted_count=2, updated_count=1
            ),
        )

    monkeypatch.setattr(module, "_load_apple_sources", fake_load_apple_sources)
    monkeypatch.setattr(module, "_sync_source", fake_sync_source)

    args = argparse.Namespace(slug="apple", limit=10, include_content=True, dry_run=True)
    await module.run(args)

    output = capsys.readouterr().out

    assert calls[0] == {"slug": "apple", "limit": 10}
    assert calls[1]["fetcher"] == "AppleFetcher"
    assert calls[1]["mapper"] == "AppleMapper"
    assert "target_sources=1" in output
    assert "jobs_inserted_total=2" in output


@pytest.mark.asyncio
async def test_import_uber_reports_failed_sources(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_import_module("import_uber_jobs.py", "import_uber_jobs_test_module")
    monkeypatch.setattr(module, "engine", _FakeEngine())

    sources = [_make_source("uber", PlatformType.UBER), _make_source("uber-2", PlatformType.UBER)]

    async def fake_load_uber_sources(*, slug, limit):  # noqa: ANN001
        _ = (slug, limit)
        return sources

    async def fake_sync_source(*, source, include_content, fetcher, mapper, dry_run):  # noqa: ANN001
        _ = (include_content, fetcher, mapper, dry_run)
        if source.identifier == "uber-2":
            return SourceSyncResult(
                source_id=str(source.id),
                source_key="uber:uber-2",
                ok=False,
                stats=SourceSyncStats(failed_count=1),
                error="fetch boom",
            )
        return SourceSyncResult(
            source_id=str(source.id),
            source_key="uber:uber",
            ok=True,
            stats=SourceSyncStats(
                fetched_count=2, mapped_count=2, unique_count=2, inserted_count=1, updated_count=1
            ),
        )

    monkeypatch.setattr(module, "_load_uber_sources", fake_load_uber_sources)
    monkeypatch.setattr(module, "_sync_source", fake_sync_source)

    args = argparse.Namespace(slug=None, limit=None, include_content=True, dry_run=False)
    await module.run(args)

    output = capsys.readouterr().out

    assert "sources_success=1" in output
    assert "sources_failed=1" in output
    assert "failed_sources=uber-2" in output
    assert "uber-2 (uber:uber-2): FAILED: fetch boom" in output


@pytest.mark.asyncio
async def test_import_tiktok_run_uses_tiktok_fetcher_and_mapper(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_import_module("import_tiktok_jobs.py", "import_tiktok_jobs_test_module")
    monkeypatch.setattr(module, "engine", _FakeEngine())

    calls: list[dict[str, object]] = []
    source = _make_source("tiktok", PlatformType.TIKTOK)

    async def fake_load_tiktok_sources(*, slug, limit):  # noqa: ANN001
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
            source_key="tiktok:tiktok",
            ok=True,
            stats=SourceSyncStats(
                fetched_count=4,
                mapped_count=4,
                unique_count=4,
                inserted_count=3,
                updated_count=1,
                closed_count=0,
            ),
        )

    monkeypatch.setattr(module, "_load_tiktok_sources", fake_load_tiktok_sources)
    monkeypatch.setattr(module, "_sync_source", fake_sync_source)

    args = argparse.Namespace(slug="tiktok", limit=5, include_content=False, dry_run=True)
    await module.run(args)

    output = capsys.readouterr().out

    assert calls[0] == {"slug": "tiktok", "limit": 5}
    assert calls[1] == {
        "identifier": "tiktok",
        "include_content": False,
        "dry_run": True,
        "fetcher": "TikTokFetcher",
        "mapper": "TikTokMapper",
    }
    assert "jobs_inserted_total=3" in output
