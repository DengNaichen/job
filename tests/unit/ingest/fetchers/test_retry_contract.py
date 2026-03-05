from __future__ import annotations

from app.ingest.fetchers.base import RetryConfig
from app.ingest.fetchers.smartrecruiters import SmartRecruitersFetcher
from app.services.application.sync.handlers import SUPPORTED_PLATFORMS


def test_default_retry_config_matches_spec_statuses(retryable_statuses: tuple[int, ...]) -> None:
    assert RetryConfig().retryable_status_codes == set(retryable_statuses)


def test_supported_platform_count_is_eight() -> None:
    assert len(SUPPORTED_PLATFORMS) == 8


def test_smartrecruiters_detail_retry_config_includes_spec_statuses(
    retryable_statuses: tuple[int, ...],
) -> None:
    detail_statuses = SmartRecruitersFetcher.detail_retry_config.retryable_status_codes
    assert set(retryable_statuses).issubset(detail_statuses), (
        "Detail retry config must include all spec transient statuses. "
        f"expected={set(retryable_statuses)}, actual={detail_statuses}"
    )
