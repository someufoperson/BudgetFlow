from enum import StrEnum


class CurrencyType(StrEnum):
    FIAT = "FIAT"
    CRYPTO = "CRYPTO"


class AccountType(StrEnum):
    STANDARD = "STANDARD"
    CREDIT = "CREDIT"


class DebtDirection(StrEnum):
    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class CategoryType(StrEnum):
    expense = "EXPENSE"
    income = "INCOME"
