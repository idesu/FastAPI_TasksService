import asyncio
import logging
import signal
import aio_pika
from app.queue.connection import rabbit
from app.config import settings
from app.db.engine import SessionFactory
from app.worker.handler import TaskHandler

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._in_flight: set[asyncio.Task] = set()

    async def _process_message(
        self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        async with message.process(requeue=False):
            async with SessionFactory() as session:
                await TaskHandler(session).handle(message.body.decode())

    async def _on_message(
        self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        # запускаем обработку как отдельную таску и трекаем её
        task = asyncio.create_task(self._process_message(message))
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)  # сам выпиливается по завершении

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)

    async def _drain(self) -> None:
        if not self._in_flight:
            return
        logger.info("draining %d in-flight tasks", len(self._in_flight))
        done, pending = await asyncio.wait(
            self._in_flight, timeout=settings.shutdown_timeout
        )
        if pending:
            # не успели за таймаут — отменяем, сообщения вернутся в очередь без ack
            logger.warning("%d tasks did not finish, cancelling", len(pending))
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def run(self) -> None:
        #self._install_signal_handlers()
        await rabbit.connect()
        queue = await rabbit.declare_task_queue()
        consumer_tag = await queue.consume(self._on_message)
        logger.info("worker started, waiting for tasks")

        try:
            await self._stop.wait()
        finally:
            logger.info("shutting down")
            await queue.cancel(consumer_tag)  # 1. перестаём забирать новые
            await self._drain()               # 2. ждём уже запущенные
            await rabbit.close()              # 3. закрываем коннект


async def main() -> None:
    await Worker().run()


if __name__ == "__main__":
    asyncio.run(main())