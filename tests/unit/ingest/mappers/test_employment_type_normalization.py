import pytest

from app.ingest.mappers.base import BaseMapper


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FullTime", "full-time"),
        ("full time", "full-time"),
        ("Regular", "full-time"),
        ("Intern", "intern"),
        ("Part time : in the field", "part-time"),
        ("full-time or part-time", "mixed"),
        ("full-time, contractor", "contract"),
        ("Fixed term", "temporary"),
        ("per diem", "per-diem"),
        ("Up to 50% work from home", "other"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_employment_type(raw: object, expected: str | None) -> None:
    assert BaseMapper._normalize_employment_type(raw) == expected
