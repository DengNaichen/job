from __future__ import annotations

from pathlib import Path

import pytest

from .helpers import (
    FETCHER_DIR,
    RETRYABLE_STATUSES,
    SUPPORTED_FETCHER_CLASS_NAMES,
    concrete_fetcher_files,
)


@pytest.fixture(scope="session")
def retryable_statuses() -> tuple[int, ...]:
    return RETRYABLE_STATUSES


@pytest.fixture(scope="session")
def fetcher_dir() -> Path:
    return FETCHER_DIR


@pytest.fixture(scope="session")
def concrete_fetchers() -> list[str]:
    return [path.name for path in concrete_fetcher_files()]


@pytest.fixture(scope="session")
def supported_fetcher_names() -> tuple[str, ...]:
    return SUPPORTED_FETCHER_CLASS_NAMES
