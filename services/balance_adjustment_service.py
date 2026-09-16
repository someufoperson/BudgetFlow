from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.transaction_time import occurred_at_from_storage, occurred_at_to_storage
from schemas.account import AccountDetails, AccountHistoryChange
from schemas.balance_adjustment import (
    AccountReconciliationResult,
    BalanceAdjustmentResult,
    BalanceAdjustmentReversalResult,
    CreateBalanceAdjustmentCommand,
    GetBalanceAdjustmentByIdCommand,
    GetBalanceAdjustmentsCommand,
    PrepareBalanceAdjustmentReversalCommand,
    ReconcileAccountCommand,
    ReverseBalanceAdjustmentCommand,
)
from services.account_service import AccountService
from services.exceptions import (
    AccountBalanceChangedError,
    BalanceAdjustmentNotFoundError,
    BalanceAdjustmentReversalChangedError,
    ServiceError,
)
from services.transaction_time import occurred_at_bounds
from settings import settings
from storage.repositories.account_repository import AccountRepository
from storage.repositories.balance_adjustment_repository import (
    BalanceAdjustmentRepository,
)


class BalanceAdjustmentService:
    def __init__(
        self,
        session: AsyncSession,
        adjustment_repository: BalanceAdjustmentRepository,
        account_repository: AccountRepository,
        account_service: AccountService,
    ) -> None:
        self._session = session
        self._adjustments = adjustment_repository
        self._accounts = account_repository
        self._account_service = account_service

    async def _reversal_result(
        self, command: PrepareBalanceAdjustmentReversalCommand
    ) -> BalanceAdjustmentReversalResult:
        original = await self._adjustments.get_by_id(command.id)
        if original is None:
            raise BalanceAdjustmentNotFoundError(command.id)
        if original.reversal_of_id is not None:
            raise ServiceError(
                "Это запись отмены. Для дальнейшего исправления выполните новую сверку."
            )
        if original.reversed_by_id is not None:
            raise ServiceError(
                f"Корректировка № {original.id} уже отменена записью № {original.reversed_by_id}."
            )
        change = await self._account_service.get_balance_change(
            AccountHistoryChange(
                account_id=original.account_id,
                occurred_at=original.occurred_at,
                amount=-original.amount,
            )
        )
        if change.amount != -original.amount:
            raise ServiceError(
                "Исходная корректировка не влияет на текущий остаток. Отмена не применена."
            )
        return BalanceAdjustmentReversalResult(
            original=BalanceAdjustmentResult.model_validate(original),
            balance_change=change,
            description=command.description,
            confirmation_id=uuid4(),
        )

    async def prepare_reverse(
        self, command: PrepareBalanceAdjustmentReversalCommand
    ) -> BalanceAdjustmentReversalResult:
        async with self._session.begin():
            await self._adjustments.begin_snapshot()
            return await self._reversal_result(command)

    async def reverse(
        self, command: ReverseBalanceAdjustmentCommand
    ) -> BalanceAdjustmentResult:
        expected = command.expected
        if command.id != expected.original.id:
            raise ServiceError("Подтверждение относится к другой корректировке.")
        try:
            async with self._session.begin():
                await self._adjustments.begin_snapshot(for_update=True)
                original = await self._adjustments.get_by_id(command.id)
                if original is None:
                    raise BalanceAdjustmentNotFoundError(command.id)
                if original.reversal is not None:
                    reversal = await self._adjustments.get_by_id(original.reversal.id)
                    if reversal is None:
                        raise ServiceError("Не удалось прочитать отмену корректировки.")
                    return BalanceAdjustmentResult.model_validate(reversal)
                current = await self._reversal_result(
                    PrepareBalanceAdjustmentReversalCommand(
                        id=command.id, description=expected.description
                    )
                )
                if current.model_dump(
                    exclude={"confirmation_id"}
                ) != expected.model_dump(exclude={"confirmation_id"}):
                    raise BalanceAdjustmentReversalChangedError(current)
                reversal = await self._adjustments.create(
                    account_id=original.account_id,
                    currency_code=original.currency_code,
                    amount=-original.amount,
                    calculated_balance=current.balance_change.account.balance,
                    actual_balance=None,
                    reconciled_at=None,
                    occurred_at=occurred_at_to_storage(datetime.now(UTC)),
                    description=expected.description,
                    confirmation_id=str(expected.confirmation_id),
                    reversal_of_id=original.id,
                )
                return BalanceAdjustmentResult.model_validate(reversal)
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось отменить корректировку. Повторите подтверждение."
            ) from error

    async def _reconcile(
        self, command: ReconcileAccountCommand
    ) -> AccountReconciliationResult:
        account = await self._account_service.require_account(
            command.account_id, command.currency_code
        )
        now = datetime.now(UTC)
        balance = await self._accounts.get_balance(account, occurred_at_to_storage(now))
        try:
            return AccountReconciliationResult(
                account=AccountDetails.model_validate(account),
                calculated_balance=balance,
                actual_balance=command.actual_balance,
                amount=command.actual_balance - balance,
                reconciled_at=now,
                opening_balance=account.opening_balance,
                opening_balance_at=occurred_at_from_storage(account.opening_balance_at),
                confirmation_id=uuid4(),
            )
        except ValidationError as error:
            raise ServiceError(
                "Сумма сверки превышает допустимую точность хранения."
            ) from error

    async def reconcile(
        self, command: ReconcileAccountCommand
    ) -> AccountReconciliationResult:
        try:
            async with self._session.begin():
                await self._adjustments.begin_snapshot()
                return await self._reconcile(command)
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось сверить остаток. Повторите запрос."
            ) from error

    async def create(
        self, command: CreateBalanceAdjustmentCommand
    ) -> BalanceAdjustmentResult | None:
        expected = command.expected
        try:
            async with self._session.begin():
                await self._adjustments.begin_snapshot(for_update=True)
                existing = await self._adjustments.get_by_confirmation_id(
                    str(expected.confirmation_id)
                )
                if existing is not None:
                    if (
                        existing.account_id != expected.account.id
                        or existing.currency_code != expected.account.currency_code
                        or existing.actual_balance != expected.actual_balance
                        or existing.calculated_balance != expected.calculated_balance
                        or existing.description != command.description
                    ):
                        raise ServiceError(
                            "Подтверждение относится к другой корректировке."
                        )
                    return BalanceAdjustmentResult.model_validate(existing)
                current = await self._reconcile(
                    ReconcileAccountCommand(
                        account_id=expected.account.id,
                        actual_balance=expected.actual_balance,
                        currency_code=expected.account.currency_code,
                    )
                )
                if (
                    current.calculated_balance != expected.calculated_balance
                    or current.account != expected.account
                    or current.opening_balance != expected.opening_balance
                    or current.opening_balance_at != expected.opening_balance_at
                ):
                    raise AccountBalanceChangedError(current)
                if current.amount == 0:
                    return None
                if current.reconciled_at <= current.opening_balance_at:
                    raise ServiceError(
                        "Повторите сверку после момента начального остатка."
                    )
                adjustment = await self._adjustments.create(
                    account_id=current.account.id,
                    currency_code=current.account.currency_code,
                    amount=current.amount,
                    calculated_balance=current.calculated_balance,
                    actual_balance=current.actual_balance,
                    reconciled_at=occurred_at_to_storage(expected.reconciled_at),
                    occurred_at=occurred_at_to_storage(current.reconciled_at),
                    description=command.description,
                    confirmation_id=str(expected.confirmation_id),
                )
                return BalanceAdjustmentResult.model_validate(adjustment)
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось применить корректировку. Повторите подтверждение."
            ) from error

    async def get_all(
        self, command: GetBalanceAdjustmentsCommand
    ) -> list[BalanceAdjustmentResult]:
        lower, upper = occurred_at_bounds(
            command.date_from, command.date_to, settings.timezone_info
        )
        async with self._session.begin():
            adjustments = await self._adjustments.get_all(
                account_id=command.account_id,
                occurred_from=lower,
                occurred_to=upper,
                offset=command.offset,
                limit=command.limit,
            )
            return [
                BalanceAdjustmentResult.model_validate(item) for item in adjustments
            ]

    async def get_by_id(
        self, command: GetBalanceAdjustmentByIdCommand
    ) -> BalanceAdjustmentResult:
        async with self._session.begin():
            adjustment = await self._adjustments.get_by_id(command.id)
            if adjustment is None:
                raise BalanceAdjustmentNotFoundError(command.id)
            return BalanceAdjustmentResult.model_validate(adjustment)
