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
    """Консьюмер задач из RabbitMQ с at-least-once семантикой.

    Жизненный цикл одного сообщения: claim задачи в БД, обработка под
    heartbeat и таймаутом, фиксация финального статуса, и только потом ack.
    Ack строго после записи статуса -> падение до ack возвращает сообщение
    в очередь, его подхватит следующий проход. Дубли доставки отсекает
    идемпотентный claim, поэтому _process обязан быть идемпотентным.
    """

    def __init__(
        self,
        rabbit: RabbitConnection,
        worker_id: str,
        prefetch: int = 10,
        heartbeat_interval: float = 60.0,
        task_timeout: float = 600.0,
    ):
        """Инициализирует воркер.

        Args:
            rabbit: общий robust-коннект; владеет им точка входа, не воркер.
            worker_id: идентификатор инстанса (в k8s — имя пода из HOSTNAME),
                пишется в task.worker_id при claim для трассировки.
            prefetch: потолок неподтверждённых сообщений на канал; он же
                ограничивает конкурентность обработки.
            heartbeat_interval: период обновления started_at в секундах,
                чтобы reclaim не счёл живую долгую задачу зависшей.
            task_timeout: верхняя граница на одну обработку; по истечении
                задача уходит в FAILED, слот освобождается.
        """
        super().__init__()
        self._rabbit = rabbit
        self._worker_id = worker_id
        self._prefetch = prefetch
        self._heartbeat_interval = heartbeat_interval
        self._task_timeout = task_timeout

    async def _loop(self) -> None:
        """Главный цикл чтения очереди.

        Выставляет qos, итерируется по сообщениям и запускает обработку
        конкурентно через _track (до prefetch штук одновременно). На stop-event
        перестаёт забирать новые сообщения, давая in-flight задачам доиграть.
        """
        channel = self._rabbit.channel
        await channel.set_qos(prefetch_count=self._prefetch)
        queue = await channel.get_queue(settings.task_queue)

        async with queue.iterator() as it:
            async for message in it:
                if self._stop.is_set():
                    break                          # на shutdown перестаём забирать новое
                self._track(self._handle(message)) # до prefetch задач конкурентно

    async def _handle(self, message: AbstractIncomingMessage) -> None:
        """Обрабатывает одно сообщение от claim до ack/reject.

        Гарантирует главный инвариант: ack только после фиксации финального
        статуса. Не удалось заклеймить -> дубль или задача уже в работе,
        просто ack. Таймаут или ошибка -> FAILED и reject в DLQ (requeue=False),
        чтобы ядовитое сообщение не крутилось вечно.

        Args:
            message: входящее сообщение; message.process гарантирует возврат
                в очередь (requeue=True) при необработанном исключении.
        """
        # requeue=True -> на любой необработанной ошибке сообщение вернётся в очередь
        async with message.process(requeue=True, ignore_processed=True):
            task_id = json.loads(message.body)["task_id"]

            # атомарный claim: NEW или PENDING или протухший IN_PROGRESS
            async with async_session_factory() as s:
                repo = TaskRepository(s)
                claimed = await repo.claim(task_id, self._worker_id)
                await s.commit()

            if not claimed:
                # если дубль доставки / уже в работе -> ack, не обрабатываем
                logger.info("task %s not claimed, skip", task_id)
                await message.ack()
                return

            # обработка с heartbeat и таймаутом
            hb = asyncio.create_task(self._heartbeat_loop(task_id))
            try:
                result = await asyncio.wait_for(
                    self._process(task_id), timeout=self._task_timeout
                )
            except asyncio.TimeoutError:
                hb.cancel()
                logger.error("task %s timed out", task_id)
                await self._finish(task_id, TaskStatus.FAILED, error="timeout")
                await message.reject(requeue=False)   # в DLQ, не вечный requeue
                return
            except Exception as exc:
                hb.cancel()
                logger.exception("task %s failed", task_id)
                await self._finish(task_id, TaskStatus.FAILED, error=str(exc))
                await message.reject(requeue=False)
                return
            else:
                hb.cancel()
                # фиксируем COMPLETED и ТОЛЬКО потом ack
                await self._finish(task_id, TaskStatus.COMPLETED, result=result)
                await message.ack()

    async def _heartbeat_loop(self, task_id: str) -> None:
        """Периодически обновляет started_at, пока задача обрабатывается.

        Сигнализирует reclaim-механизму, что задачу держит живой воркер,
        а не зависший. Отменяется по завершении обработки; CancelledError
        здесь штатный путь выхода, не ошибка.

        Args:
            task_id: идентификатор обрабатываемой задачи.
        """
        # живой воркер двигает started_at -> reclaim не переотдаст задачу как зависшую
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                async with async_session_factory() as s:
                    repo = TaskRepository(s)
                    await repo.heartbeat(task_id, self._worker_id)
                    await s.commit()
        except asyncio.CancelledError:
            pass

    async def _process(self, task_id: str) -> dict:
        """Выполняет бизнес-логику задачи и возвращает результат.

        ОБЯЗАНА быть идемпотентной: из-за at-least-once и reclaim одна задача
        может выполниться повторно. Блокирующие вызовы выносить в
        run_in_executor/to_thread, иначе встанет колом весь event loop.

        Args:
            task_id: идентификатор задачи.

        Returns:
            dict с результатом, сохраняется в task.result при COMPLETED.
        """
        ...
        return {"ok": True}

    async def _finish(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Фиксирует финальный статус задачи в отдельной короткой транзакции.

        Отдельная сессия на запись результата, а не одна транзакция на всю
        обработку: иначе соединение и блокировки держались бы минуты.

        Args:
            task_id: идентификатор задачи.
            status: COMPLETED или FAILED.
            result: payload результата при успехе.
            error: текст ошибки при провале.
        """
        # отдельная короткая транзакция: не держим соединение на всё время обработки
        async with async_session_factory() as s:
            repo = TaskRepository(s)
            await repo.set_final_status(task_id, status, result=result, error=error)
            await s.commit()

    async def _cleanup(self) -> None:
        """Хук завершения из базового Worker. Коннект гасит точка входа."""
        pass


async def main() -> None:
    """Точка входа воркера: коннект, запуск, graceful-гашение коннекта."""
    rabbit = await RabbitConnection.connect()
    worker = TaskWorker(rabbit, worker_id=os.getenv("HOSTNAME", "worker-local"))
    try:
        await worker.run()
    finally:
        await rabbit.close()


if __name__ == "__main__":
    asyncio.run(main())