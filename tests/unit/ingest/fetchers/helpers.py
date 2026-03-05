from __future__ import annotations

from pathlib import Path
import re

from app.ingest.fetchers import (
    AppleFetcher,
    AshbyFetcher,
    EightfoldFetcher,
    GreenhouseFetcher,
    LeverFetcher,
    SmartRecruitersFetcher,
    TikTokFetcher,
    UberFetcher,
)

RETRYABLE_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)

SUPPORTED_FETCHER_CLASSES = (
    GreenhouseFetcher,
    LeverFetcher,
    AshbyFetcher,
    AppleFetcher,
    UberFetcher,
    TikTokFetcher,
    EightfoldFetcher,
    SmartRecruitersFetcher,
)

SUPPORTED_FETCHER_CLASS_NAMES = tuple(cls.__name__ for cls in SUPPORTED_FETCHER_CLASSES)

REPO_ROOT = Path(__file__).resolve().parents[5]
FETCHER_DIR = REPO_ROOT / "app" / "ingest" / "fetchers"

RAW_HTTP_PATTERN = re.compile(r"client\.(get|post)\(")


def concrete_fetcher_files() -> list[Path]:
    files = sorted(FETCHER_DIR.glob("*.py"))
    return [path for path in files if path.name not in {"__init__.py", "base.py"}]


def find_raw_http_calls() -> list[tuple[str, int, str]]:
    violations: list[tuple[str, int, str]] = []
    for file_path in concrete_fetcher_files():
        for line_no, line in enumerate(file_path.read_text().splitlines(), start=1):
            if RAW_HTTP_PATTERN.search(line):
                violations.append((str(file_path.relative_to(REPO_ROOT)), line_no, line.strip()))
    return violations
