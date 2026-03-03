from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_backfill_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "backfill_job_embeddings_gemini.py"
    spec = importlib.util.spec_from_file_location("backfill_embeddings_test_module", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise RuntimeError("Unable to load backfill_job_embeddings_gemini.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_args(*, dry_run: bool = False, limit: int | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        model=None,
        dim=1024,
        batch_size=8,
        concurrency=2,
        api_batch_size=4,
        max_retries=1,
        target_tpm=0,
        max_embed_chars=12000,
        require_structured=False,
        limit=limit,
        force=False,
        dry_run=dry_run,
    )


class _FakeConn:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _target(module):
    return module.EmbeddingTargetDescriptor(
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model="gemini/gemini-embedding-001",
        embedding_dim=1024,
    )


def _config(module):
    return module.EmbeddingConfig(
        provider="gemini",
        model="gemini-embedding-001",
        api_key="test-key",
    )


@pytest.mark.asyncio
async def test_run_writes_new_active_target_rows_to_job_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backfill_module()
    fake_conn = _FakeConn()
    upsert_calls: list[list[tuple[str, str, str, str | None]]] = []

    calls = {"fetch": 0}

    async def fake_fetch_generation_batch(*_args, **_kwargs):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            return [
                module.JobRow(
                    id="job-1",
                    title="Engineer",
                    description="Write code",
                    content_fingerprint="fp-1",
                )
            ]
        return []

    async def fake_embed_batch(rows, **_kwargs):  # noqa: ANN001
        assert [row.id for row in rows] == ["job-1"]
        return [("job-1", "[0.100000000,0.200000000]")], 0

    async def fake_upsert(*_args, rows, **_kwargs):  # noqa: ANN001
        upsert_calls.append(rows)

    async def fake_connect(_dsn: str):  # noqa: ARG001
        return fake_conn

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(database_url="postgresql://db")
    )
    monkeypatch.setattr(module, "get_embedding_config", lambda: _config(module))
    monkeypatch.setattr(
        module, "resolve_active_job_embedding_target", lambda **_kwargs: _target(module)
    )
    monkeypatch.setattr(module.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(module, "_assert_embedding_schema", _async_return(None))
    monkeypatch.setattr(module, "_count_fresh_active_rows", _async_return(0))
    monkeypatch.setattr(module, "_count_pending_generation", _async_return(1))
    monkeypatch.setattr(module, "_count_missing_content_rows", _async_return(0))
    monkeypatch.setattr(module, "_fetch_generation_batch", fake_fetch_generation_batch)
    monkeypatch.setattr(module, "_embed_batch", fake_embed_batch)
    monkeypatch.setattr(module, "_upsert_active_target_rows", fake_upsert)

    await module.run(_build_args(dry_run=False))

    assert fake_conn.closed is True
    assert len(upsert_calls) == 1
    assert upsert_calls[0][0][1] == "job-1"


@pytest.mark.asyncio
async def test_run_rerun_with_no_pending_rows_skips_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backfill_module()
    fake_conn = _FakeConn()
    embed_called = {"value": False}

    async def fake_embed_batch(*_args, **_kwargs):
        embed_called["value"] = True
        return [], 0

    async def fake_fetch_generation_batch(*_args, **_kwargs):
        return []

    async def fake_connect(_dsn: str):  # noqa: ARG001
        return fake_conn

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(database_url="postgresql://db")
    )
    monkeypatch.setattr(module, "get_embedding_config", lambda: _config(module))
    monkeypatch.setattr(
        module, "resolve_active_job_embedding_target", lambda **_kwargs: _target(module)
    )
    monkeypatch.setattr(module.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(module, "_assert_embedding_schema", _async_return(None))
    monkeypatch.setattr(module, "_count_fresh_active_rows", _async_return(4))
    monkeypatch.setattr(module, "_count_pending_generation", _async_return(0))
    monkeypatch.setattr(module, "_count_missing_content_rows", _async_return(0))
    monkeypatch.setattr(module, "_fetch_generation_batch", fake_fetch_generation_batch)
    monkeypatch.setattr(module, "_embed_batch", fake_embed_batch)

    await module.run(_build_args(dry_run=False))

    assert fake_conn.closed is True
    assert embed_called["value"] is False


@pytest.mark.asyncio
async def test_run_dry_run_skips_db_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backfill_module()
    fake_conn = _FakeConn()

    fetch_calls = {"count": 0}

    async def fake_fetch_generation_batch(*_args, **_kwargs):
        fetch_calls["count"] += 1
        if fetch_calls["count"] > 1:
            return []
        return [
            module.JobRow(
                id="job-legacy",
                title="Legacy",
                description="Old",
                content_fingerprint="fp-legacy",
            ),
            module.JobRow(
                id="job-stale",
                title="Stale",
                description="Needs refresh",
                content_fingerprint="fp-new",
            ),
        ]

    observed_rows: list[list[str]] = []

    async def fake_embed_batch(rows, **_kwargs):  # noqa: ANN001
        observed_rows.append([row.id for row in rows])
        return [("job-stale", "[0.900000000,0.100000000]")], 0

    upsert_called = {"value": False}

    async def fake_upsert(*_args, **_kwargs):
        upsert_called["value"] = True

    async def fake_connect(_dsn: str):  # noqa: ARG001
        return fake_conn

    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(database_url="postgresql://db")
    )
    monkeypatch.setattr(module, "get_embedding_config", lambda: _config(module))
    monkeypatch.setattr(
        module, "resolve_active_job_embedding_target", lambda **_kwargs: _target(module)
    )
    monkeypatch.setattr(module.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(module, "_assert_embedding_schema", _async_return(None))
    monkeypatch.setattr(module, "_count_fresh_active_rows", _async_return(0))
    monkeypatch.setattr(module, "_count_pending_generation", _async_return(2))
    monkeypatch.setattr(module, "_count_missing_content_rows", _async_return(0))
    monkeypatch.setattr(module, "_fetch_generation_batch", fake_fetch_generation_batch)
    monkeypatch.setattr(module, "_embed_batch", fake_embed_batch)
    monkeypatch.setattr(module, "_upsert_active_target_rows", fake_upsert)

    await module.run(_build_args(dry_run=True))

    assert fake_conn.closed is True
    assert observed_rows == [["job-legacy", "job-stale"]]
    assert upsert_called["value"] is False
