import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractChannel, AbstractQueue
from app.config import settings


class RabbitConnection:
    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None

    async def connect(self) -> None:
        """
        connect_robust сам поднимает соединение после обрыва — это то, что закрывает требование отказоустойчивости.
        durable=True плюс persistent-сообщения, чтобы очередь пережила рестарт брокера.
        prefetch_count ограничивает, сколько неподтверждённых сообщений висит на воркере — иначе один воркер
        заберёт всю очередь.
        """
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url.unicode_string())
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=settings.worker_prefetch)

    async def declare_task_queue(self) -> AbstractQueue:
        return await self._channel.declare_queue(
            settings.task_queue, durable=True,
            arguments={"x-max-priority": 10},
        )

    @property
    def channel(self) -> AbstractChannel:
        if self._channel is None:
            raise RuntimeError("rabbit is not connected")
        return self._channel

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()


rabbit = RabbitConnection()