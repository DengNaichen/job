from app.ingest.fetchers.ashby import AshbyFetcher
from app.ingest.fetchers.apple import AppleFetcher
from app.ingest.fetchers.base import BaseFetcher
from app.ingest.fetchers.eightfold import EightfoldFetcher
from app.ingest.fetchers.github_repo import GitHubRepoFetcher
from app.ingest.fetchers.greenhouse import GreenhouseFetcher
from app.ingest.fetchers.lever import LeverFetcher
from app.ingest.fetchers.smartrecruiters import SmartRecruitersFetcher
from app.ingest.fetchers.tiktok import TikTokFetcher
from app.ingest.fetchers.uber import UberFetcher

__all__ = [
    "AshbyFetcher",
    "AppleFetcher",
    "BaseFetcher",
    "EightfoldFetcher",
    "GreenhouseFetcher",
    "GitHubRepoFetcher",
    "LeverFetcher",
    "SmartRecruitersFetcher",
    "TikTokFetcher",
    "UberFetcher",
]
