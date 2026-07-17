class ServiceError(Exception):
    """Base error service layer"""


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
