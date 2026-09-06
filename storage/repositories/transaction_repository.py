from datetime import datetime
from decimal import Decimal
from typing import TypedDict


class TransactionUpdates(TypedDict, total=False):
    name: str
    category_id: int
    amount: Decimal
    currency_code: str
    occurred_at: datetime


def matches_transaction_name(name: str, query: str | None) -> bool:
    return query is None or all(
        word in name.casefold() for word in query.casefold().split()
    )
