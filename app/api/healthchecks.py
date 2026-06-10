import asyncio
from sqlalchemy import text
from app.db.session import engine
from aio_pika import connect_robust
from app.config import settings

async def check_database():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

async def check_rabbitmq():
    try:
        # Пытаемся подключиться с таймаутом 3 секунды
        connection = await asyncio.wait_for(
            connect_robust(settings.rabbitmq_url.unicode_string()),
            timeout=3.0
        )
        await connection.close()
        return True
    except Exception as e:
        return False