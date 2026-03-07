"""FastAPI dependency injection providers.

Provides either SQL or Firestore-backed repositories depending on config.
When FIRESTORE_CREDENTIALS_FILE is set, all repositories use Firestore.
Otherwise, the legacy SQL path is used.
"""

from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from app.core.config import get_settings
from app.infrastructure.firestore_client import get_firestore_client
from app.repositories.firestore import (
    FirestoreJobEmbeddingRepository,
    FirestoreJobLocationRepository,
    FirestoreJobRepository,
    FirestoreLocationRepository,
    FirestoreSourceRepository,
    FirestoreSyncRunRepository,
)
from app.services.application.job_service import JobService
from app.services.application.source_service import SourceService


def get_db() -> AsyncClient:
    """Return the Firestore async client."""
    return get_firestore_client()


def get_job_service(db: AsyncClient = Depends(get_db)) -> JobService:
    """Firestore-backed JobService."""
    job_repo = FirestoreJobRepository(db)
    source_repo = FirestoreSourceRepository(db)
    return JobService(job_repo, source_repository=source_repo)


def get_source_service(db: AsyncClient = Depends(get_db)) -> SourceService:
    """Firestore-backed SourceService."""
    source_repo = FirestoreSourceRepository(db)
    sync_run_repo = FirestoreSyncRunRepository(db)
    job_repo = FirestoreJobRepository(db)
    return SourceService(source_repo, sync_run_repo, job_repo)
