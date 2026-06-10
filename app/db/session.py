from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import settings


# один engine на процесс — он держит пул соединений, создаётся единожды
engine: AsyncEngine = create_async_engine(
    str(settings.database_url),
    pool_timeout=30,                     # сколько ждать соединение из пула, потом ошибка
    pool_pre_ping=True,                  # пингуем перед выдачей — отсекаем мёртвые коннекты
    pool_recycle=1800,                   # пересоздаём соединение раз в 30 мин
)


# фабрика сессий — expire_on_commit=False критичен для async
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # объекты не протухают после commit -> нет ленивых подгрузок
    autoflush=False,          # flush контролируем явно, не по неявному триггеру
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: одна сессия на запрос, гарантированное закрытие."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()   # любое исключение -> откат, не оставляем грязь
            raise
        # commit НЕ здесь — границу транзакции держит сервисный слой


async def dispose_engine() -> None:
    # вызывается в lifespan при остановке — закрыть пул соединений
    await engine.dispose()