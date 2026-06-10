import asyncio
import json
import logging
import os

from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.workers.base import Worker
from app.db.session import async_session_factory
from app.rmq_queue.connection import RabbitConnection
from app.repositories.task_repository import TaskRepository
from app.models.task import TaskStatus

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


class TaskWorker(Worker):
    def __init__(
        self,
        rabbit: RabbitConnection,
        worker_id: str,
        prefetch: int = 10,
        heartbeat_interval: float = 60.0,
    ):
        super().__init__()
        self._rabbit = rabbit
        self._worker_id = worker_id
        self._prefetch = prefetch
        self._heartbeat_interval = heartbeat_interval

    async def _loop(self) -> None:
        channel = self._rabbit.channel
        # prefetch -> брокер не вываливает всю очередь в один воркер
        await channel.set_qos(prefetch_count=self._prefetch)
        queue = await channel.get_queue(settings.task_queue)

        async with queue.iterator() as it:
            async for message in it:
                if self._stop.is_set():
                    break                          # перестаём забирать новые на shutdown
                self._track(self._handle(message)) # обрабатываем конкурентно, до prefetch штук

    async def _handle(self, message: AbstractIncomingMessage) -> None:
        # requeue=True на любой необработанной ошибке -> сообщение вернётся в очередь
        async with message.process(requeue=True, ignore_processed=True):
            task_id = json.loads(message.body)["task_id"]

            # 1) атомарный claim в своей короткой транзакции
            async with async_session_factory() as s:
                repo = TaskRepository(s)
                claimed = await repo.claim(task_id, self._worker_id)
                await s.commit()

            if not claimed:
                # уже взято другим воркером / дубль доставки -> ack и выходим, не дубль
                await message.ack()
                return

            # 2) обработка с параллельным heartbeat, чтобы долгую задачу не переотдали
            hb = asyncio.create_task(self._heartbeat_loop(task_id))
            try:
                result = await self._process(task_id)
            except Exception as exc:
                hb.cancel()
                logger.exception("task %s failed", task_id)
                await self._finish(task_id, TaskStatus.FAILED, error=str(exc))
                # ядовитое -> в DLQ, не в бесконечный requeue
                await message.reject(requeue=False)
                return
            else:
                hb.cancel()
                # 3) фиксируем COMPLETED и ТОЛЬКО потом ack
                await self._finish(task_id, TaskStatus.COMPLETED, result=result)
                await message.ack()

    async def _heartbeat_loop(self, task_id: str) -> None:
        # живой воркер двигает started_at -> reclaim не переотдаст задачу как зависшую
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                async with async_session_factory() as s:
                    repo = TaskRepository(s)
                    await repo.heartbeat(task_id, self._worker_id)
                    await s.commit()
        except asyncio.CancelledError:
            pass   # обработка завершилась -> heartbeat больше не нужен

    async def _process(self, task_id: str) -> dict:
        # реальная бизнес-обработка; должна быть идемпотентной из-за at-least-once + reclaim
        return {"ok": True}

    async def _finish(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        # отдельная короткая транзакция: не держим соединение на всё время обработки
        async with async_session_factory() as s:
            repo = TaskRepository(s)
            await repo.set_final_status(task_id, status, result=result, error=error)
            await s.commit()

    async def _cleanup(self) -> None:
        # коннектом владеет точка входа; здесь чистить нечего
        pass


async def main() -> None:
    rabbit = await RabbitConnection.connect()
    worker = TaskWorker(rabbit, worker_id=os.getenv("HOSTNAME", "worker-local"))
    try:
        await worker.run()
    finally:
        await rabbit.close()


if __name__ == "__main__":
    asyncio.run(main())