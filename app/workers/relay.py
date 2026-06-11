import asyncio
import logging

from app.config import settings
from app.workers.base import Worker
from app.db.session import async_session_factory
from app.repositories.outbox_repository import OutboxRepository
from app.rmq_queue.connection import RabbitConnection
from app.rmq_queue.publisher import RabbitPublisher

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


class RelayWorker(Worker):
    def __init__(
        self,
        publisher: RabbitPublisher,
        batch_size: int = 100,
        idle_sleep: float = 1.0,
    ):
        super().__init__()
        self._publisher = publisher
        self._batch_size = batch_size
        self._idle_sleep = idle_sleep

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sent = await self._relay_batch()
            except Exception:
                # сбой базы/брокера в проходе -> не валим воркер, ждём и повторяем
                logger.exception("relay batch failed")
                await asyncio.sleep(self._idle_sleep)
                continue
            if sent == 0:
                await asyncio.sleep(self._idle_sleep)

    async def _relay_batch(self) -> int:
        async with async_session_factory() as s:
            repo = OutboxRepository(s)

            # пачка неотправленных под FOR UPDATE SKIP LOCKED
            messages = await repo.fetch_unsent(self._batch_size)
            if not messages:
                return 0

            for msg in messages:
                try:
                    # publish с publisher confirms -> ждём ack брокера
                    await self._publisher.publish(
                        task_id=str(msg.aggregate_id),
                        payload=msg.payload,
                    )
                except Exception:
                    logger.exception("publish failed for outbox %s", msg.id)
                    await repo.mark_failed(msg.id)              # retry_count++, sent_at не трогаем
                else:
                    await repo.mark_sent_and_promote(msg.id, msg.aggregate_id)  # sent_at + NEW->PENDING

            await s.commit()   # один commit на пачку; блокировки держались до сюда
            return len(messages)

    async def _cleanup(self) -> None:
        pass


async def main() -> None:
    rabbit = await RabbitConnection.connect()
    publisher = RabbitPublisher(rabbit, settings.task_queue)
    await publisher.setup()

    worker = RelayWorker(publisher, batch_size=settings.relay_batch_size)
    try:
        await worker.run()
    finally:
        await rabbit.close()


if __name__ == "__main__":
    asyncio.run(main())