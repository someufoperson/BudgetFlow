from datetime import UTC, datetime


def normalize_occurred_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("occurred_at must include a timezone")

    return value.astimezone(UTC)


def occurred_at_to_storage(value: datetime) -> datetime:
    return normalize_occurred_at(value).replace(tzinfo=None)


def occurred_at_from_storage(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
