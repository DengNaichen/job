from datetime import datetime, timezone


def to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
