import json
import aio_pika
from aio_pika import Message, DeliveryMode, ExchangeType
from app.config import settings

priority_map = {
    "HIGH": 2,
    "MEDIUM": 1,
    "LOW": 0
}

async def publish_task(task_id: str, priority: str):
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        # Объявляем очередь с поддержкой приоритетов (0-2)
        queue = await channel.declare_queue(
            settings.RABBITMQ_QUEUE,
            durable=True,
            arguments={"x-max-priority": 2}
        )
        message_body = json.dumps({"task_id": str(task_id)}).encode()
        message = Message(
            message_body,
            delivery_mode=DeliveryMode.PERSISTENT,
            priority=priority_map.get(priority, 1)
        )
        await channel.default_exchange.publish(message, routing_key=queue.name)

async def consume_tasks(callback):
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue(
            settings.RABBITMQ_QUEUE,
            durable=True,
            arguments={"x-max-priority": 2}
        )
        await queue.consume(callback)
        await asyncio.Future()  # бесконечно ждём