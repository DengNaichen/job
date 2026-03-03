from __future__ import annotations

from dataclasses import dataclass

from app.ingest.fetchers.apple import AppleFetcher
from app.ingest.fetchers.ashby import AshbyFetcher
from app.ingest.fetchers.base import BaseFetcher
from app.ingest.fetchers.eightfold import EightfoldFetcher
from app.ingest.fetchers.greenhouse import GreenhouseFetcher
from app.ingest.fetchers.lever import LeverFetcher
from app.ingest.fetchers.smartrecruiters import SmartRecruitersFetcher
from app.ingest.fetchers.tiktok import TikTokFetcher
from app.ingest.fetchers.uber import UberFetcher
from app.ingest.mappers.apple import AppleMapper
from app.ingest.mappers.ashby import AshbyMapper
from app.ingest.mappers.base import BaseMapper
from app.ingest.mappers.eightfold import EightfoldMapper
from app.ingest.mappers.greenhouse import GreenhouseMapper
from app.ingest.mappers.lever import LeverMapper
from app.ingest.mappers.smartrecruiters import SmartRecruitersMapper
from app.ingest.mappers.tiktok import TikTokMapper
from app.ingest.mappers.uber import UberMapper
from app.models import PlatformType


SUPPORTED_PLATFORMS: tuple[PlatformType, ...] = (
    PlatformType.GREENHOUSE,
    PlatformType.LEVER,
    PlatformType.ASHBY,
    PlatformType.SMARTRECRUITERS,
    PlatformType.EIGHTFOLD,
    PlatformType.APPLE,
    PlatformType.UBER,
    PlatformType.TIKTOK,
)


@dataclass(frozen=True)
class PlatformSyncHandlers:
    fetcher_cls: type[BaseFetcher]
    mapper_cls: type[BaseMapper]


PLATFORM_SYNC_HANDLERS: dict[PlatformType, PlatformSyncHandlers] = {
    PlatformType.GREENHOUSE: PlatformSyncHandlers(GreenhouseFetcher, GreenhouseMapper),
    PlatformType.LEVER: PlatformSyncHandlers(LeverFetcher, LeverMapper),
    PlatformType.ASHBY: PlatformSyncHandlers(AshbyFetcher, AshbyMapper),
    PlatformType.SMARTRECRUITERS: PlatformSyncHandlers(
        SmartRecruitersFetcher, SmartRecruitersMapper
    ),
    PlatformType.EIGHTFOLD: PlatformSyncHandlers(EightfoldFetcher, EightfoldMapper),
    PlatformType.APPLE: PlatformSyncHandlers(AppleFetcher, AppleMapper),
    PlatformType.UBER: PlatformSyncHandlers(UberFetcher, UberMapper),
    PlatformType.TIKTOK: PlatformSyncHandlers(TikTokFetcher, TikTokMapper),
}
