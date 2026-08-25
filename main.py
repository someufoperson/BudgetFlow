import asyncio

from pydantic import ValidationError
from requests import RequestException

from ai.assistant import Assistant
from ai.client import AIClient
from services.category_service import CategoryService
from services.currency_service import CurrencyService
from services.exceptions import ServiceError
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService
from storage.db import async_session_factory, engine
from storage.migrations import upgrade_database
from storage.repositories.category_repository import CategoryRepository
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.expense_transaction_repository import (
    ExpenseTransactionRepository,
)
from storage.repositories.incoming_transaction_repository import (
    IncomingTransactionRepository,
)


async def run_console() -> None:
    ai_client = AIClient()

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

        expense_service = ExpenseTransactionService(
            session=session,
            transaction_repository=ExpenseTransactionRepository(session),
            currency_repository=currency_repository,
            category_service=category_service,
        )

        incoming_service = IncomingTransactionService(
            session=session,
            transaction_repository=IncomingTransactionRepository(session),
            currency_repository=currency_repository,
            category_service=category_service,
        )

        assistant = Assistant(
            client=ai_client,
            currency_service=currency_service,
            expense_service=expense_service,
            incoming_service=incoming_service,
            category_service=category_service,
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
        await run_console()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    upgrade_database()
    asyncio.run(main())
