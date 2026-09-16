from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from schemas.account import GetAllAccountsCommand
from schemas.report import (
    GetReportCommand,
    ReportAdjustmentResult,
    ReportCategoryResult,
    ReportCurrencyResult,
    ReportPeriodResult,
    ReportResult,
)
from services.account_service import AccountService
from services.exceptions import ServiceError
from services.transaction_time import occurred_at_bounds
from settings import settings
from storage.repositories.report_repository import ReportRepository


class ReportService:
    def __init__(
        self,
        session: AsyncSession,
        report_repository: ReportRepository,
        account_service: AccountService,
    ) -> None:
        self._session = session
        self._reports = report_repository
        self._accounts = account_service

    async def get(self, command: GetReportCommand) -> ReportResult:
        now = datetime.now(settings.timezone_info)
        end = command.date_to or now.date()
        start = command.date_from or end - timedelta(days=(command.days or 30) - 1)
        if end > now.date():
            raise ServiceError("Конец отчёта не может быть в будущем.")
        occurred_from, occurred_to = occurred_at_bounds(
            start, end, settings.timezone_info
        )
        if occurred_from is None or occurred_to is None:
            raise ServiceError("Укажите полный период отчёта.")
        days = (end - start).days + 1
        step = (days + 5) // 6
        periods = [
            ReportPeriodResult(
                date_from=start + timedelta(days=offset),
                date_to=min(start + timedelta(days=offset + step - 1), end),
            )
            for offset in range(0, days, step)
        ]
        bounds: list[tuple[datetime, datetime]] = []
        for period in periods:
            lower, upper = occurred_at_bounds(
                period.date_from, period.date_to, settings.timezone_info
            )
            if lower is not None and upper is not None:
                bounds.append((lower, upper))
        currencies: dict[str, ReportCurrencyResult] = {}
        async with self._session.begin():
            for code, count, increase, decrease in await self._reports.get_adjustments(
                occurred_from, occurred_to
            ):
                section = currencies.setdefault(
                    code, ReportCurrencyResult(currency_code=code)
                )
                section.adjustment_count = count
                section.adjustment_increase = increase
                section.adjustment_decrease = decrease
                section.adjustment_total = increase - decrease
            for (
                code,
                adjustment_id,
                original_id,
                reversed_id,
            ) in await self._reports.get_adjustment_links(occurred_from, occurred_to):
                currencies[code].adjustment_links.append(
                    ReportAdjustmentResult(
                        id=adjustment_id,
                        reversal_of_id=original_id,
                        reversed_by_id=reversed_id,
                    )
                )
            for income in (True, False):
                for code, amount, count, unassigned in await self._reports.get_totals(
                    occurred_from, occurred_to, income=income
                ):
                    section = currencies.setdefault(
                        code, ReportCurrencyResult(currency_code=code)
                    )
                    if income:
                        section.income = amount
                    else:
                        section.expense = amount
                    section.count += count
                    section.unassigned_count += unassigned
            for code, name, amount in await self._reports.get_categories(
                occurred_from, occurred_to
            ):
                currencies[code].categories.append(
                    ReportCategoryResult(name=name, amount=amount)
                )
            for section in currencies.values():
                section.periods = [period.model_copy() for period in periods]
            for code, index, amount in await self._reports.get_periods(bounds):
                currencies[code].periods[index].amount = amount
        accounts = await self._accounts.get_all(
            GetAllAccountsCommand(include_inactive=True)
        )
        for account in accounts:
            section = currencies.setdefault(
                account.currency_code,
                ReportCurrencyResult(currency_code=account.currency_code),
            )
            section.accounts.append(account)
        for section in currencies.values():
            section.difference = section.income - section.expense
            section.balance = sum(
                (account.balance for account in section.accounts), Decimal("0.00")
            )
            if not section.periods:
                section.periods = [period.model_copy() for period in periods]
            section.categories.sort(key=lambda item: (-item.amount, item.name))
        return ReportResult(
            date_from=start,
            date_to=end,
            balance_at=now,
            currencies=[currencies[code] for code in sorted(currencies)],
        )

    @staticmethod
    def format_adjustment_link(item: ReportAdjustmentResult) -> str:
        if item.reversal_of_id is not None:
            return f"Отмена № {item.id} корректировки № {item.reversal_of_id}"
        return f"Корректировка № {item.id} отменена записью № {item.reversed_by_id}"

    @classmethod
    def format_adjustment_links(cls, report: ReportResult) -> str:
        lines: list[str] = []
        for section in report.currencies:
            if section.adjustment_links:
                lines.append(
                    f"{section.currency_code}: связи отмен (статус на сейчас). Суммы учитываются по датам записей."
                )
                lines.extend(
                    cls.format_adjustment_link(item)
                    for item in section.adjustment_links
                )
        return "\n".join(lines)

    @staticmethod
    def format_amount(amount: Decimal) -> str:
        return f"{amount:,.2f}".replace(",", " ").replace(".", ",")

    @classmethod
    def format_text(cls, report: ReportResult) -> str:
        lines = [f"Отчёт · {report.date_from:%d.%m.%Y} — {report.date_to:%d.%m.%Y}"]
        if not report.currencies:
            return lines[0] + "\nЗа период операций нет. Счетов пока нет."
        for section in report.currencies:
            lines.extend(
                [
                    f"\n{section.currency_code} · операций: {section.count}",
                    f"Доходы: {cls.format_amount(section.income)}",
                    f"Расходы: {cls.format_amount(section.expense)}",
                    f"Разница: {cls.format_amount(section.difference)}",
                ]
            )
            if not section.count:
                lines.append(
                    "За период доходов и расходов нет."
                    if section.adjustment_count
                    else "За период операций нет."
                )
            if section.adjustment_count:
                lines.extend(
                    [
                        f"Корректировки остатков за период: {section.adjustment_count}",
                        (
                            f"Увеличение: {cls.format_amount(section.adjustment_increase)}; "
                            f"уменьшение: {cls.format_amount(section.adjustment_decrease)}; "
                            f"итог: {cls.format_amount(section.adjustment_total)}"
                        ),
                        "Корректировки не включены в доходы и расходы. Подробности: «покажи корректировки».",
                    ]
                )
            if section.adjustment_links:
                lines.append(
                    "Связи отмен (статус на сейчас; суммы учитываются по датам записей):"
                )
                lines.extend(
                    cls.format_adjustment_link(item)
                    for item in section.adjustment_links
                )
            if section.categories:
                lines.append("Расходы по категориям:")
                lines.extend(
                    f"• {item.name}: {cls.format_amount(item.amount)} "
                    f"({item.amount * 100 / section.expense:.1f}%)"
                    for item in section.categories
                )
            if section.expense:
                lines.append("Динамика расходов:")
                lines.extend(
                    f"• {item.date_from:%d.%m}–{item.date_to:%d.%m}: "
                    f"{cls.format_amount(item.amount)}"
                    for item in section.periods
                )
            lines.append(
                f"На счетах сейчас ({report.balance_at:%d.%m.%Y %H:%M %z}): "
                f"{cls.format_amount(section.balance)}"
            )
            lines.extend(
                f"• {account.name}{' [неактивен]' if not account.is_active else ''}: "
                f"{cls.format_amount(account.balance)}"
                for account in section.accounts
            )
            if section.unassigned_count:
                lines.append(
                    f"Операций без счёта: {section.unassigned_count}. "
                    "Включены в обороты, но не в остатки счетов."
                )
        lines.append(
            "\nОстатки включают неактивные счета; лимиты и карточки долгов не прибавляются."
        )
        return "\n".join(lines)
