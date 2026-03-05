from __future__ import annotations

from app.ingest.fetchers import AppleFetcher, AshbyFetcher, EightfoldFetcher, GreenhouseFetcher, LeverFetcher
from app.ingest.fetchers import SmartRecruitersFetcher, TikTokFetcher, UberFetcher

from .helpers import find_raw_http_calls

GROUP_A_FILES = ("greenhouse.py", "lever.py", "ashby.py", "smartrecruiters.py")
GROUP_B_FILES = ("apple.py", "uber.py", "tiktok.py", "eightfold.py")

GROUP_A_FETCHERS = (GreenhouseFetcher, LeverFetcher, AshbyFetcher, SmartRecruitersFetcher)
GROUP_B_FETCHERS = (AppleFetcher, UberFetcher, TikTokFetcher, EightfoldFetcher)


def _raw_calls_for_files(file_names: tuple[str, ...]) -> list[tuple[str, int, str]]:
    return [
        violation
        for violation in find_raw_http_calls()
        if violation[0].rsplit("/", 1)[-1] in file_names
    ]


def test_group_a_fetchers_have_no_raw_http_calls() -> None:
    violations = _raw_calls_for_files(GROUP_A_FILES)
    assert violations == [], f"Group A fetchers still have raw calls: {violations}"


def test_group_b_fetchers_have_no_raw_http_calls() -> None:
    violations = _raw_calls_for_files(GROUP_B_FILES)
    assert violations == [], f"Group B fetchers still have raw calls: {violations}"


def test_group_a_fetchers_retry_matrix_includes_spec_statuses(
    retryable_statuses: tuple[int, ...],
) -> None:
    expected = set(retryable_statuses)
    for fetcher_cls in GROUP_A_FETCHERS:
        assert expected.issubset(fetcher_cls().retry_config.retryable_status_codes)


def test_group_b_fetchers_retry_matrix_includes_spec_statuses(
    retryable_statuses: tuple[int, ...],
) -> None:
    expected = set(retryable_statuses)
    for fetcher_cls in GROUP_B_FETCHERS:
        assert expected.issubset(fetcher_cls().retry_config.retryable_status_codes)
