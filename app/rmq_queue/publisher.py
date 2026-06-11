import json
import logging

import aio_pika
from aio_pika.abc import AbstractExchange

from app.rmq_queue.connection import RabbitConnection

logger = logging.getLogger(__name__)


class RabbitPublisher:
    def __init__(self, rabbit: RabbitConnection, queue_name: str):
        self._rabbit = rabbit
        self._queue_name = queue_name
        self._exchange: AbstractExchange | None = None

    async def setup(self) -> None:
        # идемпотентно: durable queue + DLX для ядовитых сообщений
        channel = self._rabbit.channel
        await channel.declare_queue(
            self._queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": f"{self._queue_name}.dlq",
            },
        )
        await channel.declare_queue(f"{self._queue_name}.dlq", durable=True)
        # default exchange -> routing_key = имя очереди
        self._exchange = channel.default_exchange

    async def publish(self, task_id: str, payload: dict) -> None:
        if self._exchange is None:
            raise RuntimeError("publisher not set up")

        message = aio_pika.Message(
            body=json.dumps({"task_id": task_id, **payload}).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,   # сообщение переживёт рестарт брокера
            content_type="application/json",
            message_id=task_id,        # для дедупликации/трассировки на стороне consumer
        )
        # publisher_confirms включён на канале -> await вернётся ТОЛЬКО после ack брокера
        await self._exchange.publish(message, routing_key=self._queue_name)