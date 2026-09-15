import asyncio
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from requests import RequestException

from ai.assistant import Assistant
from ai.client import AIClient
from ai.memory import ConversationMemory
from schemas.document import DocumentInput
from services.account_service import AccountService
from services.balance_adjustment_service import BalanceAdjustmentService
from services.category_service import CategoryService
from services.currency_service import CurrencyService
from services.debt_service import DebtService
from services.document_service import DocumentService
from services.exceptions import ServiceError
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService
from services.report_service import ReportService
from services.transfer_transaction_service import TransferTransactionService
from settings import settings
from storage.db import async_session_factory, engine
from storage.migrations import upgrade_database
from storage.repositories.account_repository import AccountRepository
from storage.repositories.balance_adjustment_repository import (
    BalanceAdjustmentRepository,
)
from storage.repositories.category_repository import CategoryRepository
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.debt_repository import DebtRepository
from storage.repositories.expense_transaction_repository import (
    ExpenseTransactionRepository,
)
from storage.repositories.incoming_transaction_repository import (
    IncomingTransactionRepository,
)
from storage.repositories.report_repository import ReportRepository
from storage.repositories.transfer_transaction_repository import (
    TransferTransactionRepository,
)


async def run_console() -> None:
    ai_client = AIClient()
    conversation_memory = ConversationMemory(settings.context_max_pairs)

    async with async_session_factory() as session:
        currency_repository = CurrencyRepository(session)
        category_repository = CategoryRepository(session)

        currency_service = CurrencyService(
            session=session,
            currency_repository=currency_repository,
        )

        category_service = CategoryService(
            session=session,
            category_repository=category_repository,
        )

        account_service = AccountService(
            session, AccountRepository(session), currency_repository
        )

        expense_service = ExpenseTransactionService(
            session=session,
            transaction_repository=ExpenseTransactionRepository(session),
            currency_repository=currency_repository,
            category_service=category_service,
            account_service=account_service,
        )

        incoming_service = IncomingTransactionService(
            session=session,
            transaction_repository=IncomingTransactionRepository(session),
            currency_repository=currency_repository,
            category_service=category_service,
            account_service=account_service,
        )

        assistant = Assistant(
            client=ai_client,
            currency_service=currency_service,
            expense_service=expense_service,
            incoming_service=incoming_service,
            category_service=category_service,
            memory=conversation_memory,
            account_service=account_service,
            debt_service=DebtService(
                session,
                DebtRepository(session),
                currency_repository,
                AccountRepository(session),
            ),
            report_service=ReportService(
                session, ReportRepository(session), account_service
            ),
            transfer_service=TransferTransactionService(
                session, TransferTransactionRepository(session), account_service
            ),
            adjustment_service=BalanceAdjustmentService(
                session,
                BalanceAdjustmentRepository(session),
                AccountRepository(session),
                account_service,
            ),
        )

        print("💰 BudgetFlow запущен.")
        print("Для выхода введите exit.")
        print('Для загрузки скриншота: /скриншот "путь к файлу"')

        while True:
            try:
                user_message = input("\nВы: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Завершение работы")
                break

            if user_message.lower() in {"exit", "quit"}:
                print("👋 Завершение работы")
                break

            if not user_message:
                continue

            try:
                command = user_message.split(maxsplit=1)
                if command[0].casefold() in {"/скриншот", "/screenshot"}:
                    if len(command) != 2:
                        raise ServiceError('Укажите путь: /скриншот "путь к файлу"')
                    filename = command[1].strip()
                    if filename.startswith(('"', "'")):
                        if len(filename) < 2 or filename[-1] != filename[0]:
                            raise ServiceError("Закройте кавычки вокруг пути к файлу.")
                        filename = filename[1:-1]
                    if not filename:
                        raise ServiceError("Укажите путь к изображению.")
                    path = Path(filename).expanduser()
                    try:
                        if not path.is_file():
                            raise ServiceError(
                                "Изображение не найдено. Укажите путь к файлу."
                            )
                        with path.open("rb") as source:
                            data = await asyncio.to_thread(
                                source.read, DocumentService.MAX_BYTES + 1
                            )
                    except (OSError, ValueError) as error:
                        raise ServiceError(
                            "Не удалось открыть изображение. Проверьте путь и права доступа."
                        ) from error
                    answer = await assistant.handle_attachments(
                        [DocumentInput(name=path.name, data=data)]
                    )
                else:
                    answer = await assistant.handle_message(user_message)
                if assistant.report_images:
                    directory = Path("output/reports")
                    try:
                        directory.mkdir(parents=True, exist_ok=True)
                        for image in assistant.report_images:
                            target = directory / f"{uuid4().hex}-{image.name}"
                            await asyncio.to_thread(target.write_bytes, image.data)
                            answer += f"\nИзображение: {target.resolve()}"
                    except OSError as error:
                        raise ServiceError(
                            "Не удалось сохранить PNG в output/reports. Проверьте права записи."
                        ) from error
                    finally:
                        assistant.report_images = []
            except ValidationError:
                answer = "⚠️ AI вернул некорректный JSON"
            except RequestException as error:
                answer = f"⚠️ Ошибка обращения к AI: {error}"
            except ServiceError as error:
                answer = f"⚠️ {error}"

            print(f"BudgetFlow: {answer}")


async def main() -> None:
    try:
        await run_console()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    upgrade_database()
    asyncio.run(main())
