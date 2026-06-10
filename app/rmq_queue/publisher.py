import json
import aio_pika
from uuid import UUID
from app.config import settings
from app.rmq_queue.connection import rabbit


async def publish_task(task_id: UUID, priority: int) -> None:
    message = aio_pika.Message(
        body=json.dumps({"task_id": str(task_id)}).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # сообщение на диск
        priority=priority,
    )
    await rabbit._channel.default_exchange.publish(
        message, routing_key=settings.task_queue,
    )