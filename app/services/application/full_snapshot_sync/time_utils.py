from datetime import datetime

from app.core.time import to_naive_utc as core_to_naive_utc
from app.core.time import utc_now_naive


def to_naive_utc(value: datetime | None) -> datetime | None:
    return core_to_naive_utc(value)


def now_naive_utc() -> datetime:
    return utc_now_naive()
