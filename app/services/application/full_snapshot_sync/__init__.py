from app.contracts.sync import SourceSyncResult, SourceSyncStats
from app.services.domain.location import get_geonames_resolver as _get_domain_geonames_resolver

from .errors import FullSnapshotSyncError
from .service import FullSnapshotSyncService


def get_geonames_resolver():
    return _get_domain_geonames_resolver()


__all__ = [
    "FullSnapshotSyncError",
    "FullSnapshotSyncService",
    "SourceSyncResult",
    "SourceSyncStats",
    "get_geonames_resolver",
]
