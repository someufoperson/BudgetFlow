from datetime import UTC, date, datetime, time, timedelta, tzinfo

from domain.transaction_time import normalize_occurred_at, occurred_at_to_storage
from services.exceptions import FutureTransactionDateError


def resolve_occurred_at(value: datetime | None) -> datetime:
    now = datetime.now(UTC)

    if value is None:
        return occurred_at_to_storage(now)

    occurred_at = normalize_occurred_at(value)
    if occurred_at > now:
        raise FutureTransactionDateError(occurred_at)

    return occurred_at_to_storage(occurred_at)


def occurred_at_bounds(
    date_from: date | None,
    date_to: date | None,
    timezone: tzinfo,
) -> tuple[datetime | None, datetime | None]:
    occurred_from = None
    occurred_to = None

    if date_from is not None:
        occurred_from = occurred_at_to_storage(
            datetime.combine(date_from, time.min, tzinfo=timezone)
        )

    if date_to is not None:
        occurred_to = occurred_at_to_storage(
            datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone)
        )

    return occurred_from, occurred_to
