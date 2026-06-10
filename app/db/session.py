from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import SessionFactory


async def get_session() -> AsyncIterator[AsyncSession]:
    '''
    Dыдача сессии с гарантированным закрытием.

    Транзакцией управляет вызывающий код.
    cессия просто открывается и гарантированно закрывается через контекст.
    '''
    async with SessionFactory() as session:
        yield session