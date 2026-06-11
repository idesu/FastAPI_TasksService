import asyncio
import os
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


from app.models.base import Base

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test_tasks:test_password@localhost:5433/test_tasks",
)

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://test_tasks:test_password@localhost:5433/test_tasks",
)


@pytest.fixture(scope="session")
def event_loop():
    # один loop на сессию -> session-scoped async-фикстуры живут между тестами
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """Коннект к Postgres, поднятому СНАРУЖИ (docker compose / CI service).

    Контейнером управляет compose или CI, не тест. URL из env.
    drop_all перед create_all -> чистая схема, даже если контейнер
    долгоживущий и остался с прошлого прогона.
    """
    url = TEST_DATABASE_URL   # postgresql+asyncpg://test:test@localhost:5433/test
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Сессия в транзакции с откатом после каждого теста.

    Внешняя транзакция + вложенный SAVEPOINT: тест может коммитить внутри,
    но всё откатывается в конце -> чистая база между тестами без пересоздания схемы.
    """
    connection = await pg_engine.connect()
    trans = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    await connection.begin_nested()

    @event.listens_for(session.sync_session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        # внутренний commit закрыл SAVEPOINT -> переоткрываем, внешняя транзакция жива
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()      # откатываем всё, что натворил тест
        await connection.close()


@pytest_asyncio.fixture
async def session_factory(pg_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Фабрика независимых сессий для тестов конкуренции.

    Каждый вызов — своя транзакция со своим коннектом, чтобы два claim
    реально конкурировали на уровне БД (SKIP LOCKED), а не делили транзакцию.
    """
    return async_sessionmaker(pg_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def bind_session_factory(pg_engine: AsyncEngine):
    """Перенаправляет глобальную async_session_factory на тестовый engine.

    Воркеры (relay, task) открывают сессии через модульную фабрику, а не
    принимают её снаружи -> иначе ходят в прод-URL и падают gaierror.
    Восстанавливаем оригинал, чтобы подмена не текла между тестами.
    """
    import app.db.session as db_module

    test_factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    original = db_module.async_session_factory
    db_module.async_session_factory = test_factory
    try:
        yield test_factory
    finally:
        db_module.async_session_factory = original


class FakePublisher:
    """Успешный publisher-заглушка: копит опубликованное, не ходит в раббит."""

    def __init__(self):
        self.published: list[dict] = []

    async def setup(self) -> None:
        pass

    async def publish(self, task_id: str, payload: dict) -> None:
        self.published.append({"task_id": task_id, **payload})


class FailingPublisher:
    """Падающий publisher: эмулирует отказ брокера до confirm."""

    async def setup(self) -> None:
        pass

    async def publish(self, task_id: str, payload: dict) -> None:
        raise ConnectionError("broker down")


@pytest.fixture
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def failing_publisher() -> FailingPublisher:
    return FailingPublisher()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(pg_engine):
    """Чистим таблицы ПЕРЕД каждым тестом, который коммитит по-настоящему.

    db_session-тесты откатываются сами, но bind_session_factory/session_factory
    коммитят в живой Postgres -> между тестами надо чистить вручную,
    иначе строки протекают и ломают scalar_one / счётчики.
    """
    async with pg_engine.begin() as conn:
        # TRUNCATE с RESTART IDENTITY и CASCADE -> быстро и сбрасывает sequence
        await conn.execute(text("TRUNCATE outbox_messages, tasks RESTART IDENTITY CASCADE"))
    yield