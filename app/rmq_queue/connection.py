import logging

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel

from app.config import settings

logger = logging.getLogger(__name__)


class RabbitConnection:
    def __init__(self, connection: AbstractRobustConnection, channel: AbstractRobustChannel):
        self._connection = connection
        self.channel = channel

    @classmethod
    async def connect(cls) -> "RabbitConnection":
        # robust -> сам переподключается при обрыве и восстанавливает каналы/консьюмеры
        connection = await aio_pika.connect_robust(
            str(settings.rabbitmq_url),
            timeout=10,
        )
        # publisher_confirms=True -> publish ждёт подтверждения брокера (нужно для outbox)
        channel = await connection.channel(publisher_confirms=True)
        # global prefetch не ставим тут — это дело consumer-канала воркера
        logger.info("rabbit connected")
        return cls(connection, channel)

    async def close(self) -> None:
        await self._connection.close()
        logger.info("rabbit closed")