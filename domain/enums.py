from enum import StrEnum


class CurrencyType(StrEnum):
    FIAT = "FIAT"
    CRYPTO = "CRYPTO"


class CategoryType(StrEnum):
    expense = "EXPENSE"
    income = "INCOME"
