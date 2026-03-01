from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceSyncStats:
    fetched_count: int = 0
    mapped_count: int = 0
    unique_count: int = 0
    deduped_by_external_id: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    closed_count: int = 0
    failed_count: int = 0


@dataclass
class SourceSyncResult:
    source_id: str
    source_key: str
    ok: bool
    stats: SourceSyncStats = field(default_factory=SourceSyncStats)
    error: str | None = None
