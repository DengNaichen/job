from __future__ import annotations

from .helpers import find_raw_http_calls


def test_supported_fetcher_registry_count_is_eight(supported_fetcher_names: tuple[str, ...]) -> None:
    assert len(supported_fetcher_names) == 8


def test_concrete_fetchers_do_not_use_raw_client_get_or_post() -> None:
    violations = find_raw_http_calls()
    assert violations == [], (
        "Concrete fetchers must use BaseFetcher retry wrappers. "
        f"Found raw HTTP calls: {violations}"
    )
