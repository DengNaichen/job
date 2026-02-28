from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

from app.models import PlatformType, Source, SyncRun, SyncRunStatus


def _load_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "run_scheduled_ingests.py"
    spec = importlib.util.spec_from_file_location("run_scheduled_ingests_test_module", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("Unable to load run_scheduled_ingests.py")
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


def _make_sync_run(
    source: str,
    status: SyncRunStatus,
    *,
    fetched_count: int = 0,
    unique_count: int = 0,
    deduped_by_external_id: int = 0,
    inserted_count: int = 0,
    updated_count: int = 0,
    closed_count: int = 0,
    error_summary: str | None = None,
) -> SyncRun:
    return SyncRun(
        source=source,
        status=status,
        fetched_count=fetched_count,
        unique_count=unique_count,
        deduped_by_external_id=deduped_by_external_id,
        inserted_count=inserted_count,
        updated_count=updated_count,
        closed_count=closed_count,
        error_summary=error_summary,
    )


@pytest.mark.asyncio
async def test_run_scheduled_ingests_reports_success_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "engine", _FakeEngine())

    source = _make_source("airbnb", PlatformType.GREENHOUSE)

    async def fake_load_candidate_sources(*, platform, identifier, limit):  # noqa: ANN001
        assert platform is None
        assert identifier is None
        assert limit is None
        return [source], []

    class FakeSyncService:
        def __init__(self, engine):  # noqa: ANN001
            self.engine = engine

        async def sync_source(self, *, source, include_content, dry_run, retry_attempts):  # noqa: ANN001
            assert include_content is True
            assert dry_run is False
            assert retry_attempts == 3
            return _make_sync_run(
                "greenhouse:airbnb",
                SyncRunStatus.success,
                fetched_count=5,
                unique_count=4,
                deduped_by_external_id=1,
                inserted_count=2,
                updated_count=1,
                closed_count=1,
            )

    monkeypatch.setattr(module, "_load_candidate_sources", fake_load_candidate_sources)
    monkeypatch.setattr(module, "SyncService", FakeSyncService)

    exit_code = await module.run(
        argparse.Namespace(
            platform=None,
            identifier=None,
            limit=None,
            include_content=True,
            dry_run=False,
            retry_attempts=3,
        )
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "target_sources=1" in output
    assert "status=success" in output
    assert "jobs_inserted_total=2" in output
    assert "jobs_closed_total=1" in output


@pytest.mark.asyncio
async def test_run_scheduled_ingests_continues_on_failures_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "engine", _FakeEngine())

    sources = [
        _make_source("airbnb", PlatformType.GREENHOUSE),
        _make_source("stripe", PlatformType.LEVER),
    ]

    async def fake_load_candidate_sources(*, platform, identifier, limit):  # noqa: ANN001
        _ = (platform, identifier, limit)
        return sources, []

    class FakeSyncService:
        def __init__(self, engine):  # noqa: ANN001
            self.engine = engine

        async def sync_source(self, *, source, include_content, dry_run, retry_attempts):  # noqa: ANN001
            _ = (include_content, dry_run, retry_attempts)
            if source.identifier == "stripe":
                return _make_sync_run(
                    "lever:stripe",
                    SyncRunStatus.failed,
                    error_summary="fetch boom",
                )
            return _make_sync_run(
                "greenhouse:airbnb",
                SyncRunStatus.success,
                fetched_count=2,
                unique_count=2,
                inserted_count=1,
                updated_count=1,
            )

    monkeypatch.setattr(module, "_load_candidate_sources", fake_load_candidate_sources)
    monkeypatch.setattr(module, "SyncService", FakeSyncService)

    exit_code = await module.run(
        argparse.Namespace(
            platform=None,
            identifier=None,
            limit=None,
            include_content=False,
            dry_run=True,
            retry_attempts=2,
        )
    )

    output = capsys.readouterr().out

    assert exit_code == 1
    assert "sources_success=1" in output
    assert "sources_failed=1" in output
    assert "failed_sources=stripe" in output
    assert "status=failed, error=fetch boom" in output


@pytest.mark.asyncio
async def test_run_scheduled_ingests_rejects_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "engine", _FakeEngine())

    exit_code = await module.run(
        argparse.Namespace(
            platform="workday",
            identifier=None,
            limit=None,
            include_content=True,
            dry_run=False,
            retry_attempts=3,
        )
    )

    output = capsys.readouterr().out

    assert exit_code == 1
    assert "unsupported_platform=workday" in output


@pytest.mark.asyncio
async def test_run_scheduled_ingests_warns_about_unsupported_sources(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "engine", _FakeEngine())

    source = _make_source("airbnb", PlatformType.GREENHOUSE)
    unsupported = _make_source("acme", PlatformType.WORKDAY)

    async def fake_load_candidate_sources(*, platform, identifier, limit):  # noqa: ANN001
        _ = (platform, identifier, limit)
        return [source], [unsupported]

    class FakeSyncService:
        def __init__(self, engine):  # noqa: ANN001
            self.engine = engine

        async def sync_source(self, *, source, include_content, dry_run, retry_attempts):  # noqa: ANN001
            _ = (source, include_content, dry_run, retry_attempts)
            return _make_sync_run("greenhouse:airbnb", SyncRunStatus.success)

    monkeypatch.setattr(module, "_load_candidate_sources", fake_load_candidate_sources)
    monkeypatch.setattr(module, "SyncService", FakeSyncService)

    exit_code = await module.run(
        argparse.Namespace(
            platform=None,
            identifier=None,
            limit=None,
            include_content=True,
            dry_run=False,
            retry_attempts=3,
        )
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "warning_unsupported_sources=workday:acme" in output
