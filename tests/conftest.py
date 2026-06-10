import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.base import Base
from app.config import settings


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    # отдельная тестовая база, не та, что в dev
    eng = create_async_engine(str(settings.test_database_url), poolclass=None)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    # каждый тест в своей транзакции, в конце rollback -> чистая база
    connection = await engine.connect()
    trans = await connection.begin()
    factory = async_sessionmaker(bind=connection, expire_on_commit=False)
    async with factory() as s:
        yield s
    await trans.rollback()
    await connection.close()