from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from settings import settings

engine = create_async_engine(f"sqlite+aiosqlite:///./{settings.db_name}", echo=False)


@event.listens_for(engine.sync_engine, "connect")
def enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,  # noqa: ARG001
) -> None:
    cursor = dbapi_connection.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        cursor.close()


async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
