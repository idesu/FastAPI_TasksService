import logging
from aio_pika import connect_robust, ExchangeType, Channel
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel
from app.config import settings

logger = logging.getLogger(__name__)


class RabbitConnection:
    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None

    @classmethod
    async def connect(cls) -> "RabbitConnection":
        self = cls()
        await self._open()
        return self

    async def _open(self) -> None:
        # connect_robust сам переподключается при обрыве сети/рестарте брокера
        self._connection = await connect_robust(
            str(settings.rabbitmq_url),     # amqp://user:pass@host:5672/vhost
            timeout=10,
        )
        self._channel = await self._connection.channel(publisher_confirms=True)
        # publisher confirms: publish() ждёт ack от брокера, иначе сообщение не считается отправленным
        await self._declare_topology(self._channel)
        logger.info("rabbit connected")

    async def _declare_topology(self, channel: Channel) -> None:
        # топология объявляется идемпотентно при каждом коннекте — переживает рестарт брокера
        exchange = await channel.declare_exchange(
            "tasks", ExchangeType.DIRECT, durable=True   # durable -> переживёт рестарт
        )
        # DLX для ядовитых сообщений: reject(requeue=False) уводит сюда, не в цикл
        dlx = await channel.declare_exchange("tasks.dlx", ExchangeType.DIRECT, durable=True)
        dlq = await channel.declare_queue("tasks.dlq", durable=True)
        await dlq.bind(dlx, routing_key="tasks")

        queue = await channel.declare_queue(
            "tasks",
            durable=True,                 # очередь переживёт рестарт брокера
            arguments={
                "x-max-priority": 10,                 # приоритеты LOW/MEDIUM/HIGH
                "x-dead-letter-exchange": "tasks.dlx",  # куда уходят rejected
            },
        )
        await queue.bind(exchange, routing_key="tasks")

    @property
    def channel(self) -> AbstractRobustChannel:
        if self._channel is None or self._channel.is_closed:
            raise RuntimeError("rabbit channel is not available")
        return self._channel

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("rabbit connection closed")