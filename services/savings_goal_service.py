from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import SavingsGoalStatus
from domain.transaction_time import occurred_at_from_storage, occurred_at_to_storage
from schemas.savings_goal import (
    AllocateSavingsGoalCommand,
    CreateSavingsGoalCommand,
    GetAllSavingsGoalsCommand,
    GetSavingsGoalByIdCommand,
    ReleaseSavingsGoalCommand,
    SavingsGoalAccountResult,
    SavingsGoalAllocationResult,
    SavingsGoalResult,
    UpdateSavingsGoalCommand,
)
from services.exceptions import (
    AccountNotFoundError,
    AccountUnavailableError,
    CurrencyNotFoundError,
    SavingsGoalNotFoundError,
    ServiceError,
)
from settings import settings
from storage.models.savings_goal import SavingsGoal
from storage.repositories.account_repository import AccountRepository
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.savings_goal_allocation_repository import (
    SavingsGoalAllocationRepository,
)
from storage.repositories.savings_goal_repository import (
    SavingsGoalRepository,
    SavingsGoalUpdates,
)


class SavingsGoalService:
    def __init__(
        self,
        session: AsyncSession,
        goal_repository: SavingsGoalRepository,
        allocation_repository: SavingsGoalAllocationRepository,
        currency_repository: CurrencyRepository,
        account_repository: AccountRepository,
    ) -> None:
        self._session = session
        self._goals = goal_repository
        self._allocations = allocation_repository
        self._currencies = currency_repository
        self._accounts = account_repository

    async def create(self, command: CreateSavingsGoalCommand) -> SavingsGoalResult:
        try:
            async with self._session.begin():
                await self._goals.begin_write()
                if (
                    await self._currencies.get_currency_by_code(command.currency_code)
                    is None
                ):
                    raise CurrencyNotFoundError(command.currency_code)
                goal = await self._goals.create(
                    name=command.name,
                    target_amount_minor=int(command.target_amount * 100),
                    currency_code=command.currency_code,
                    due_date=command.due_date,
                    priority=command.priority,
                )
                return await self._result(goal)
        except (IntegrityError, OperationalError) as error:
            raise ServiceError(
                "Не удалось сохранить цель. Повторите запрос."
            ) from error

    async def get_all(
        self, command: GetAllSavingsGoalsCommand
    ) -> list[SavingsGoalResult]:
        async with self._session.begin():
            await self._goals.begin_snapshot()
            return [await self._result(goal) for goal in await self._goals.get_all()]

    async def get_by_id(self, command: GetSavingsGoalByIdCommand) -> SavingsGoalResult:
        async with self._session.begin():
            await self._goals.begin_snapshot()
            goal = await self._goals.get_by_id(command.id)
            if goal is None:
                raise SavingsGoalNotFoundError(command.id)
            return await self._result(goal)

    async def update(self, command: UpdateSavingsGoalCommand) -> SavingsGoalResult:
        try:
            async with self._session.begin():
                await self._goals.begin_write()
                goal = await self._goals.get_by_id(command.id)
                if goal is None:
                    raise SavingsGoalNotFoundError(command.id)
                allocated = sum(
                    item.amount_minor
                    for item in await self._allocations.get_all(goal_id=goal.id)
                )
                target = (
                    int(command.target_amount * 100)
                    if command.target_amount is not None
                    else goal.target_amount_minor
                )
                if target < allocated:
                    raise ServiceError(
                        "Сначала освободите деньги: новая сумма ниже выделенной."
                    )
                if command.status is SavingsGoalStatus.PAUSED and target == allocated:
                    raise ServiceError("Достигнутую цель нельзя приостановить.")
                status = command.status or goal.status
                if target == allocated:
                    status = SavingsGoalStatus.ACHIEVED
                elif status is SavingsGoalStatus.ACHIEVED:
                    status = SavingsGoalStatus.ACTIVE
                updates: SavingsGoalUpdates = {
                    "target_amount_minor": target,
                    "status": status,
                }
                if command.name is not None:
                    updates["name"] = command.name
                if command.priority is not None:
                    updates["priority"] = command.priority
                if "due_date" in command.model_fields_set:
                    updates["due_date"] = command.due_date
                updated = await self._goals.update(goal.id, updates)
                if updated is None:
                    raise SavingsGoalNotFoundError(goal.id)
                return await self._result(updated)
        except (IntegrityError, OperationalError) as error:
            raise ServiceError("Не удалось изменить цель. Повторите запрос.") from error

    async def allocate(self, command: AllocateSavingsGoalCommand) -> SavingsGoalResult:
        return await self._change_allocation(command)

    async def release(self, command: ReleaseSavingsGoalCommand) -> SavingsGoalResult:
        return await self._change_allocation(command)

    async def _change_allocation(
        self, command: AllocateSavingsGoalCommand | ReleaseSavingsGoalCommand
    ) -> SavingsGoalResult:
        try:
            async with self._session.begin():
                await self._goals.begin_write()
                goal = await self._goals.get_by_id(command.id)
                if goal is None:
                    raise SavingsGoalNotFoundError(command.id)
                if command.currency_code != goal.currency_code:
                    raise ServiceError("Валюта суммы не совпадает с валютой цели.")
                allocations = await self._allocations.get_all(goal_id=goal.id)
                amounts: dict[int, int] = {}
                for item in allocations:
                    amounts[item.account_id] = (
                        amounts.get(item.account_id, 0) + item.amount_minor
                    )
                account_id = command.account_id
                if account_id is None:
                    sources = [key for key, value in amounts.items() if value > 0]
                    if len(sources) != 1:
                        raise ServiceError(
                            "Уточните счёт для освобождения денег из цели."
                        )
                    account_id = sources[0]
                account = await self._accounts.get_by_id(account_id)
                if account is None:
                    raise AccountNotFoundError(account_id)
                if account.currency_code != goal.currency_code:
                    raise AccountUnavailableError(
                        "Валюты счёта и цели должны совпадать."
                    )
                amount_minor = int(command.amount * 100)
                allocated = sum(amounts.values())
                if isinstance(command, AllocateSavingsGoalCommand):
                    if not account.is_active:
                        raise AccountUnavailableError(
                            "Для выделения выберите активный счёт."
                        )
                    if goal.status is not SavingsGoalStatus.ACTIVE:
                        raise ServiceError(
                            "Выделение возможно только на активную цель."
                        )
                    if allocated + amount_minor > goal.target_amount_minor:
                        raise ServiceError(
                            "Выделение превышает сумму цели. Сначала увеличьте цель."
                        )
                    balance = await self._accounts.get_balance(
                        account, occurred_at_to_storage(datetime.now(UTC))
                    )
                    total = (
                        Decimal(
                            sum(
                                item.amount_minor
                                for item in await self._allocations.get_all(
                                    account_id=account_id
                                )
                            )
                        )
                        / 100
                    )
                    available = max(Decimal(0), balance - total)
                    if command.amount > available:
                        shortfall = max(Decimal(0), total - max(Decimal(0), balance))
                        raise ServiceError(
                            f"Недостаточно доступных средств: {available:.2f} {goal.currency_code}. "
                            f"Нехватка покрытия выделений: {shortfall:.2f}. "
                            "Пересмотрите выделения или пополните счёт."
                        )
                else:
                    if amount_minor > amounts.get(account_id, 0):
                        raise ServiceError(
                            "Нельзя освободить больше, чем выделено с этого счёта."
                        )
                    amount_minor = -amount_minor
                await self._allocations.create(goal.id, account_id, amount_minor)
                allocated += amount_minor
                status = goal.status
                if allocated == goal.target_amount_minor:
                    status = SavingsGoalStatus.ACHIEVED
                elif status is SavingsGoalStatus.ACHIEVED:
                    status = SavingsGoalStatus.ACTIVE
                updated = await self._goals.update(goal.id, {"status": status})
                if updated is None:
                    raise SavingsGoalNotFoundError(goal.id)
                return await self._result(updated)
        except (IntegrityError, OperationalError) as error:
            raise ServiceError("Выделение не изменено. Повторите запрос.") from error

    async def _result(self, goal: SavingsGoal) -> SavingsGoalResult:
        allocations = await self._allocations.get_all(goal_id=goal.id)
        amounts: dict[int, int] = {}
        for item in allocations:
            amounts[item.account_id] = (
                amounts.get(item.account_id, 0) + item.amount_minor
            )
        accounts: list[SavingsGoalAccountResult] = []
        names: dict[int, str] = {}
        now = occurred_at_to_storage(datetime.now(UTC))
        for account_id, amount in amounts.items():
            account = await self._accounts.get_by_id(account_id)
            if account is None:
                raise AccountNotFoundError(account_id)
            names[account_id] = account.name
            if amount == 0:
                continue
            balance = await self._accounts.get_balance(account, now)
            total = (
                Decimal(
                    sum(
                        item.amount_minor
                        for item in await self._allocations.get_all(
                            account_id=account_id
                        )
                    )
                )
                / 100
            )
            accounts.append(
                SavingsGoalAccountResult(
                    account_id=account_id,
                    account_name=account.name,
                    is_active=account.is_active,
                    allocated_amount=Decimal(amount) / 100,
                    balance=balance,
                    total_allocated_amount=total,
                    available_amount=max(Decimal(0), balance - total),
                    shortfall_amount=max(Decimal(0), total - max(Decimal(0), balance)),
                )
            )
        target = Decimal(goal.target_amount_minor) / 100
        allocated = Decimal(sum(amounts.values())) / 100
        return SavingsGoalResult(
            id=goal.id,
            name=goal.name,
            target_amount=target,
            currency_code=goal.currency_code,
            due_date=goal.due_date,
            priority=goal.priority,
            status=goal.status,
            allocated_amount=allocated,
            remaining_amount=target - allocated,
            progress_percent=allocated / target * 100,
            is_overdue=(
                goal.due_date is not None
                and goal.due_date < datetime.now(settings.timezone_info).date()
                and allocated < target
            ),
            accounts=accounts,
            history=[
                SavingsGoalAllocationResult(
                    id=item.id,
                    account_id=item.account_id,
                    account_name=names[item.account_id],
                    amount=Decimal(item.amount_minor) / 100,
                    created_at=occurred_at_from_storage(item.created_at),
                )
                for item in allocations
            ],
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )
