from datetime import datetime


class ServiceError(Exception):
    """Base error service layer"""


class AccountNotFoundError(ServiceError):
    def __init__(self, account_id: int) -> None:
        super().__init__(f"Счёт {account_id} не найден.")
        self.account_id = account_id


class AccountUnavailableError(ServiceError):
    pass


class DebtNotFoundError(ServiceError):
    def __init__(self, debt_id: int) -> None:
        super().__init__(f"Долг {debt_id} не найден.")
        self.debt_id = debt_id


class DebtChangedError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "Карточка долга изменилась после выбора. Выберите её заново для удаления."
        )


class TransactionChangedError(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "Операция изменилась после выбора. Найдите её заново и повторите правку."
        )


class CurrencyNotFoundError(ServiceError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Currency {code} not found")
        self.code = code


class CurrencyAlreadyExistsError(ServiceError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Currency {code} already exists")
        self.code = code


class ExpenseTransactionNotFoundError(ServiceError):
    def __init__(self, transaction_id: int) -> None:
        super().__init__(f"Expense transaction {transaction_id} not found")
        self.transaction_id = transaction_id


class IncomingTransactionNotFoundError(ServiceError):
    def __init__(self, transaction_id: int) -> None:
        super().__init__(f"Incoming transaction {transaction_id} not found")
        self.transaction_id = transaction_id


class CategoryNotFoundError(ServiceError):
    def __init__(self, category_id: int) -> None:
        super().__init__(f"Category {category_id} not found")
        self.category_id = category_id


class CategoryAlreadyExistsError(ServiceError):
    def __init__(self, name: str, direction: str) -> None:
        super().__init__(f"Category {name!r} already exists for direction {direction}")
        self.name = name
        self.direction = direction


class CategoryInUseError(ServiceError):
    def __init__(self, category_id: int) -> None:
        super().__init__(
            f"Category {category_id} cannot be deleted because it is used by transactions"
        )
        self.category_id = category_id


class CategoryDirectionMismatchError(ServiceError):
    def __init__(self, category_id: int, expected_direction: str) -> None:
        super().__init__(
            f"Category {category_id} must have direction {expected_direction}"
        )
        self.category_id = category_id
        self.expected_direction = expected_direction


class CategoryDirectionChangeInUseError(ServiceError):
    def __init__(self, category_id: int) -> None:
        super().__init__(
            f"Category {category_id} direction cannot be changed because the category "
            "is used by transactions"
        )
        self.category_id = category_id


class FutureTransactionDateError(ServiceError):
    def __init__(self, occurred_at: datetime) -> None:
        super().__init__("Transaction date cannot be in the future")
        self.occurred_at = occurred_at
