class BudgetFlowError(Exception):
    """Base exception for expected application errors."""


class CurrencyError(BudgetFlowError):
    """Base exception for currency-related error."""
