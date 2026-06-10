from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings

engine = create_async_engine(
    settings.database_url.unicode_string(),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # проверяет коннект перед выдачей, спасает от "server closed connection"
    echo=False,
)

SessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)