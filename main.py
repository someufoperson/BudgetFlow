import asyncio

from pydantic import ValidationError
from requests import RequestException

from ai.assistant import Assistant
from ai.client import AIClient
from services.exceptions import ServiceError
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService
from storage.db import async_session_factory, engine
from storage.models.base import Base
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.expense_transaction_repository import (
    ExpenseTransactionRepository,
)
from storage.repositories.incoming_transaction_repository import (
    IncomingTransactionRepository,
)

# Импорты нужны для регистрации моделей в Base.metadata
import storage.models.currency  # noqa: F401
import storage.models.expense_transaction  # noqa: F401
import storage.models.incoming_transaction  # noqa: F401


async def create_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def run_console() -> None:
    ai_client = AIClient()

    async with async_session_factory() as session:
        currency_repository = CurrencyRepository(session)

        expense_service = ExpenseTransactionService(
            session=session,
            transaction_repository=ExpenseTransactionRepository(session),
            currency_repository=currency_repository,
        )

        incoming_service = IncomingTransactionService(
            session=session,
            transaction_repository=IncomingTransactionRepository(session),
            currency_repository=currency_repository,
        )

        assistant = Assistant(
            client=ai_client,
            expense_service=expense_service,
            incoming_service=incoming_service,
        )

        print("BudgetFlow запущен.")
        print("Для выхода введите exit.")

        while True:
            try:
                user_message = input("\nВы: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nЗаврешение работы")
                break

            if user_message.lower() in {"exit", "quit"}:
                print("Завершение работы")
                break

            if not user_message:
                continue

            try:
                answer = await assistant.handle_message(
                    user_message,
                )
            except ValidationError:
                answer = "AI вернул некорректный JSON"
            except RequestException as error:
                answer = f"Ошибка обращения к AI: {error}"
            except ServiceError as error:
                answer = str(error)

            print(f"BudgetFlow: {answer}")


async def main() -> None:
    try:
        await create_tables()
        await run_console()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
