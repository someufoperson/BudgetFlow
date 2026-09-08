from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.transaction_time import occurred_at_to_storage
from schemas.account import (
    AccountResult,
    AssignAccountTransactionsCommand,
    CreateAccountCommand,
    GetAccountByIdCommand,
    GetAllAccountsCommand,
    UpdateAccountCommand,
)
from services.exceptions import (
    AccountNotFoundError,
    AccountUnavailableError,
    CurrencyNotFoundError,
    ServiceError,
)
from services.transaction_time import resolve_occurred_at
from storage.models.account import Account
from storage.repositories.account_repository import AccountRepository, AccountUpdates
from storage.repositories.currency_repository import CurrencyRepository


class AccountService:
    def __init__(
        self,
        session: AsyncSession,
        account_repository: AccountRepository,
        currency_repository: CurrencyRepository,
    ) -> None:
        self._session = session
        self._accounts = account_repository
        self._currencies = currency_repository

    async def require_account(
        self, account_id: int | None, currency_code: str
    ) -> Account:
        account = (
            await self._accounts.get_by_id(account_id)
            if account_id is not None
            else await self._accounts.get_default()
        )
        if account is None:
            if account_id is not None:
                raise AccountNotFoundError(account_id)
            raise AccountUnavailableError(
                "Создайте счёт и выберите счёт по умолчанию либо укажите счёт операции."
            )
        if not account.is_active:
            raise AccountUnavailableError("Счёт деактивирован. Выберите активный счёт.")
        if account.currency_code != currency_code:
            raise AccountUnavailableError(
                "Валюта операции не совпадает с валютой счёта. Уточните счёт."
            )
        return account

    async def create(self, command: CreateAccountCommand) -> AccountResult:
        try:
            async with self._session.begin():
                if (
                    await self._currencies.get_currency_by_code(command.currency_code)
                    is None
                ):
                    raise CurrencyNotFoundError(command.currency_code)
                accounts = await self._accounts.get_all(include_inactive=True)
                if any(
                    account.name.casefold() == command.name.casefold()
                    for account in accounts
                ):
                    raise ServiceError("Счёт с таким названием уже существует.")
                account = await self._accounts.create(
                    command.name,
                    command.currency_code,
                    command.opening_balance,
                    resolve_occurred_at(command.opening_balance_at),
                    is_default=not accounts,
                    account_type=command.account_type,
                    credit_limit=command.credit_limit,
                )
                return await self._result(account)
        except IntegrityError as error:
            raise ServiceError(
                "Не удалось создать счёт: название или счёт по умолчанию уже заняты."
            ) from error

    async def _result(self, account: Account) -> AccountResult:
        result = AccountResult.model_validate(account)
        result.balance = await self._accounts.get_balance(
            account, occurred_at_to_storage(datetime.now(UTC))
        )
        return result

    async def get_all(self, command: GetAllAccountsCommand) -> list[AccountResult]:
        async with self._session.begin():
            accounts = await self._accounts.get_all(
                include_inactive=command.include_inactive
            )
            return [await self._result(account) for account in accounts]

    async def get_by_id(self, command: GetAccountByIdCommand) -> AccountResult:
        async with self._session.begin():
            account = await self._accounts.get_by_id(command.id)
            if account is None:
                raise AccountNotFoundError(command.id)
            return await self._result(account)

    async def update(self, command: UpdateAccountCommand) -> AccountResult:
        try:
            async with self._session.begin():
                account = await self._accounts.get_by_id(command.id)
                if account is None:
                    raise AccountNotFoundError(command.id)
                updates: AccountUpdates = {}
                if command.opening_balance is not None:
                    updates["opening_balance"] = command.opening_balance
                if (
                    command.account_type is not None
                    or "credit_limit" in command.model_fields_set
                ):
                    try:
                        terms = CreateAccountCommand(
                            name=account.name,
                            currency_code=account.currency_code,
                            opening_balance=account.opening_balance,
                            account_type=command.account_type or account.account_type,
                            credit_limit=(
                                command.credit_limit
                                if "credit_limit" in command.model_fields_set
                                else account.credit_limit
                            ),
                        )
                    except ValidationError as error:
                        raise ServiceError(
                            "Для кредитного счёта нужен неотрицательный лимит; "
                            "для обычного счёта лимит должен отсутствовать."
                        ) from error
                    updates["account_type"] = terms.account_type
                    updates["credit_limit"] = terms.credit_limit
                if command.name is not None:
                    accounts = await self._accounts.get_all(include_inactive=True)
                    if any(
                        item.id != command.id
                        and item.name.casefold() == command.name.casefold()
                        for item in accounts
                    ):
                        raise ServiceError("Счёт с таким названием уже существует.")
                    updates["name"] = command.name
                if command.is_active is not None:
                    updates["is_active"] = command.is_active
                    if not command.is_active:
                        updates["is_default"] = False
                if command.is_default is not None:
                    if command.is_default and not updates.get(
                        "is_active", account.is_active
                    ):
                        raise AccountUnavailableError(
                            "Нельзя выбрать деактивированный счёт по умолчанию."
                        )
                    updates["is_default"] = command.is_default
                updated = await self._accounts.update(command.id, updates)
                if updated is None:
                    raise AccountNotFoundError(command.id)
                return await self._result(updated)
        except IntegrityError as error:
            raise ServiceError(
                "Не удалось изменить счёт: конфликт названия или счёта по умолчанию."
            ) from error

    async def assign_transactions(
        self, command: AssignAccountTransactionsCommand
    ) -> int:
        async with self._session.begin():
            account = await self._accounts.get_by_id(command.id)
            if account is None:
                raise AccountNotFoundError(command.id)
            if not account.is_active:
                raise AccountUnavailableError("Сначала восстановите счёт.")
            return await self._accounts.assign_transactions(account)
