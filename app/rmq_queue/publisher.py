import json
from typing import Protocol

from uuid import UUID

from aio_pika import Message, DeliveryMode

from app.config import settings
from app.rmq_queue.connection import rabbit, RabbitConnection


class Publisher(Protocol):
    # интерфейс, на который завязан сервис — не конкретная реализация
    async def publish(self, task_id: str, priority: int) -> None: ...


class RabbitPublisher:
    def __init__(self, rabbit: RabbitConnection, queue_name: str = settings.task_queue) -> None:
        self._rabbit = rabbit
        self._queue_name = queue_name

    async def publish(self, task_id: UUID, priority: int) -> None:
        message = Message(
            body=json.dumps({"task_id": task_id}).encode(),
            priority=priority,
            delivery_mode=DeliveryMode.PERSISTENT,  # переживёт рестарт брокера
        )
        await self._rabbit.channel.default_exchange.publish(
            message, routing_key=self._queue_name
        )