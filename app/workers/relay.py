import asyncio
from sqlalchemy import select, update, func

from app.config import settings
from app.rmq_queue.connection import RabbitConnection
from app.workers.base import Worker
from app.db.session import async_session_factory
from app.models.outbox import OutboxMessage
from app.models.task import Task, TaskStatus
from app.rmq_queue.publisher import Publisher, RabbitPublisher

_PRIORITY = {"LOW": 1, "MEDIUM": 5, "HIGH": 10}


class RelayWorker(Worker):
    def __init__(self, publisher: Publisher, batch: int = 100, idle_delay: float = 1.0):
        super().__init__()
        self._publisher = publisher
        self._batch = batch
        self._idle_delay = idle_delay

    async def _loop(self) -> None:
        while not self._stop.is_set():
            sent = await self._relay_batch()
            if sent == 0:
                # очередь пуста — спим, но просыпаемся сразу если пришёл стоп
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._idle_delay)
                except asyncio.TimeoutError:
                    pass

    async def _relay_batch(self) -> int:
        async with async_session_factory() as s:
            rows = (await s.execute(
                select(OutboxMessage).where(OutboxMessage.sent_at.is_(None))
                .order_by(OutboxMessage.created_at)
                .with_for_update(skip_locked=True)   # несколько relay не дерутся
                .limit(self._batch)
            )).scalars().all()

            if not rows:
                return 0

            for msg in rows:
                try:
                    await self._publisher.publish(
                        msg.payload["task_id"], _PRIORITY[msg.payload["priority"]]
                    )
                    msg.sent_at = func.now()
                    await s.execute(
                        update(Task)
                        .where(Task.id == msg.aggregate_id, Task.status == TaskStatus.NEW)
                        .values(status=TaskStatus.PENDING)
                    )
                except Exception:
                    msg.retry_count += 1   # publish упал — оставляем неотправленным, retry позже
            await s.commit()
            return len(rows)

    async def _cleanup(self) -> None:
        await self._publisher.close()

async def main() -> None:
    rabbit = await RabbitConnection.connect()
    publisher = RabbitPublisher(rabbit, settings.task_queue)
    worker = RelayWorker(publisher)
    try:
        await worker.run()
    finally:
        await rabbit.close()


if __name__ == "__main__":
    asyncio.run(main())