from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import DebtDirection
from schemas.debt import (
    CreateDebtCommand,
    DebtResult,
    DebtSummaryResult,
    DeleteDebtCommand,
    GetAllDebtsCommand,
    GetDebtByIdCommand,
    UpdateDebtCommand,
)
from services.exceptions import (
    AccountNotFoundError,
    AccountUnavailableError,
    CurrencyNotFoundError,
    DebtChangedError,
    DebtNotFoundError,
    ServiceError,
)
from settings import settings
from storage.repositories.account_repository import AccountRepository
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.debt_repository import DebtRepository, DebtUpdates


class DebtService:
    def __init__(
        self,
        session: AsyncSession,
        debt_repository: DebtRepository,
        currency_repository: CurrencyRepository,
        account_repository: AccountRepository,
    ) -> None:
        self._session = session
        self._debts = debt_repository
        self._currencies = currency_repository
        self._accounts = account_repository

    async def create(self, command: CreateDebtCommand) -> DebtResult:
        today = datetime.now(settings.timezone_info).date()
        as_of_date = command.as_of_date or today
        if as_of_date > today:
            raise ServiceError("Дата актуальности долга не может быть в будущем.")
        try:
            async with self._session.begin():
                await self.require_currency_and_account(
                    command.currency_code, command.account_id
                )
                debt = await self._debts.create(
                    name=command.name,
                    direction=command.direction,
                    amount=command.amount,
                    currency_code=command.currency_code,
                    as_of_date=as_of_date,
                    priority=command.priority,
                    account_id=command.account_id,
                    counterparty=command.counterparty,
                    due_date=command.due_date,
                    description=command.description,
                )
                return DebtResult.model_validate(debt)
        except IntegrityError as error:
            raise ServiceError(
                "Не удалось сохранить долг: проверьте валюту и счёт."
            ) from error

    async def require_currency_and_account(
        self, currency_code: str, account_id: int | None
    ) -> None:
        if await self._currencies.get_currency_by_code(currency_code) is None:
            raise CurrencyNotFoundError(currency_code)
        if account_id is not None:
            account = await self._accounts.get_by_id(account_id)
            if account is None:
                raise AccountNotFoundError(account_id)
            if account.currency_code != currency_code:
                raise AccountUnavailableError(
                    "Валюта долга не совпадает с валютой счёта."
                )

    async def get_all(self, command: GetAllDebtsCommand) -> list[DebtResult]:
        async with self._session.begin():
            debts = await self._debts.get_all(include_repaid=command.include_repaid)
            return [DebtResult.model_validate(debt) for debt in debts]

    async def get_by_id(self, command: GetDebtByIdCommand) -> DebtResult:
        async with self._session.begin():
            debt = await self._debts.get_by_id(command.id)
            if debt is None:
                raise DebtNotFoundError(command.id)
            return DebtResult.model_validate(debt)

    @staticmethod
    def get_summary(debts: list[DebtResult]) -> DebtSummaryResult:
        result = DebtSummaryResult()
        for debt in debts:
            if debt.amount == 0:
                continue
            amounts = (
                result.payable
                if debt.direction is DebtDirection.PAYABLE
                else result.receivable
            )
            amounts[debt.currency_code] = (
                amounts.get(debt.currency_code, Decimal("0.00")) + debt.amount
            )
        return result

    async def delete(self, command: DeleteDebtCommand) -> None:
        async with self._session.begin():
            debt = await self._debts.get_by_id(command.id)
            if debt is None:
                raise DebtNotFoundError(command.id)
            snapshot = command.expected
            if DebtResult.model_validate(debt) != snapshot:
                raise DebtChangedError()
            expected: DebtUpdates = {
                "name": snapshot.name,
                "direction": snapshot.direction,
                "amount": snapshot.amount,
                "currency_code": snapshot.currency_code,
                "as_of_date": snapshot.as_of_date,
                "priority": snapshot.priority,
                "account_id": snapshot.account_id,
                "counterparty": snapshot.counterparty,
                "due_date": snapshot.due_date,
                "description": snapshot.description,
            }
            if not await self._debts.delete(command.id, expected):
                raise DebtChangedError()

    async def update(self, command: UpdateDebtCommand) -> DebtResult:
        today = datetime.now(settings.timezone_info).date()
        if command.as_of_date is not None and command.as_of_date > today:
            raise ServiceError("Дата актуальности долга не может быть в будущем.")
        try:
            async with self._session.begin():
                debt = await self._debts.get_by_id(command.id)
                if debt is None:
                    raise DebtNotFoundError(command.id)
                currency_code = command.currency_code or debt.currency_code
                account_id = (
                    command.account_id
                    if "account_id" in command.model_fields_set
                    else debt.account_id
                )
                await self.require_currency_and_account(currency_code, account_id)
                updates: DebtUpdates = {}
                if command.name is not None:
                    updates["name"] = command.name
                if command.direction is not None:
                    updates["direction"] = command.direction
                if command.amount is not None:
                    updates["amount"] = command.amount
                    updates["as_of_date"] = command.as_of_date or today
                if command.currency_code is not None:
                    updates["currency_code"] = command.currency_code
                if command.as_of_date is not None:
                    updates["as_of_date"] = command.as_of_date
                if command.priority is not None:
                    updates["priority"] = command.priority
                if "account_id" in command.model_fields_set:
                    updates["account_id"] = command.account_id
                if "counterparty" in command.model_fields_set:
                    updates["counterparty"] = command.counterparty
                if "due_date" in command.model_fields_set:
                    updates["due_date"] = command.due_date
                if "description" in command.model_fields_set:
                    updates["description"] = command.description
                updated = await self._debts.update(command.id, updates)
                if updated is None:
                    raise DebtNotFoundError(command.id)
                return DebtResult.model_validate(updated)
        except IntegrityError as error:
            raise ServiceError(
                "Не удалось изменить долг: проверьте валюту и счёт."
            ) from error
