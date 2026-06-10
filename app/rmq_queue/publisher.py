import json
from typing import Protocol
from aio_pika import Message, DeliveryMode
from app.rmq_queue.connection import RabbitConnection


class Publisher(Protocol):
    # интерфейс, на который завязан relay — не конкретная реализация
    async def publish(self, task_id: str, priority: int) -> None: ...
    async def close(self) -> None: ...


class RabbitPublisher:
    def __init__(self, rabbit: RabbitConnection, queue_name: str = "tasks"):
        self._rabbit = rabbit
        self._queue_name = queue_name

    async def publish(self, task_id: str, priority: int) -> None:
        message = Message(
            body=json.dumps({"task_id": task_id}).encode(),
            priority=priority,                      # x-max-priority очереди -> LOW/MEDIUM/HIGH
            delivery_mode=DeliveryMode.PERSISTENT,  # сброс на диск, переживёт рестарт брокера
            content_type="application/json",
            message_id=task_id,                     # для трассировки и дедупликации на консьюмере
        )
        # publish через канал с publisher_confirms=True -> ждём ack брокера
        await self._rabbit.channel.default_exchange.publish(
            message,
            routing_key=self._queue_name,
            # mandatory: если сообщение некуда смаршрутить — получим ошибку, а не молча потеряем
            mandatory=True,
        )

    async def close(self) -> None:
        # коннектом владеет RabbitConnection; здесь закрывать нечего
        # метод есть в интерфейсе ради симметрии и подмены реализаций
        ...