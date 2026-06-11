import asyncio
import time
from contextlib import asynccontextmanager


class FakeIncomingMessage:
    """Заглушка aio_pika.AbstractIncomingMessage для тестов воркера.

    Повторяет ровно тот интерфейс, что трогает _handle: body, ack, reject
    и process() как async-контекст. Дополнительно фиксирует ТАЙМИНГ
    подтверждения -> тест может проверить, что ack случился после записи статуса.
    """

    def __init__(self, body: bytes, message_id: str | None = None):
        self.body = body
        self.message_id = message_id
        self.acked = False
        self.rejected = False
        self.requeue_on_reject: bool | None = None
        self.ack_ts: float | None = None       # когда подтвердили — для проверки порядка
        self.process_entered = False

    async def ack(self) -> None:
        if self.acked or self.rejected:
            # двойное подтверждение -> баг в коде воркера, тест должен упасть
            raise RuntimeError("message already finalized")
        self.acked = True
        self.ack_ts = time.monotonic()

    async def reject(self, requeue: bool = True) -> None:
        if self.acked or self.rejected:
            raise RuntimeError("message already finalized")
        self.rejected = True
        self.requeue_on_reject = requeue
        self.ack_ts = time.monotonic()

    async def nack(self, requeue: bool = True) -> None:
        await self.reject(requeue=requeue)

    @asynccontextmanager
    async def process(self, requeue: bool = True, ignore_processed: bool = False):
        """Имитация aio_pika message.process().

        На необработанном исключении внутри блока реджектит с requeue,
        как настоящий контекст-менеджер aio-pika.
        """
        self.process_entered = True
        try:
            yield self
        except Exception:
            if not (self.acked or self.rejected):
                await self.reject(requeue=requeue)
            raise
        else:
            if ignore_processed and not (self.acked or self.rejected):
                # если код сам не ack/reject — оставляем как есть, не падаем
                pass


class FakeQueue:
    """Очередь-заглушка: отдаёт сообщения воркеру через async-итератор."""

    def __init__(self):
        self._channel_q: asyncio.Queue = asyncio.Queue()
        self._consuming = asyncio.Event()

    def iterator(self):
        return _FakeQueueIterator(self._channel_q, self._consuming)

    async def put(self, message) -> None:
        await self._channel_q.put(message)


class _FakeQueueIterator:
    """async-контекст + async-итератор, как queue.iterator() у aio-pika."""

    def __init__(self, q: asyncio.Queue, consuming: asyncio.Event):
        self._q = q
        self._consuming = consuming

    async def __aenter__(self):
        self._consuming.set()      # сигналим тесту, что потребление началось
        return self

    async def __aexit__(self, *exc):
        self._consuming.clear()
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        # ждём сообщение; CancelledError на shutdown штатно завершит итерацию
        return await self._q.get()


class FakeChannel:
    def __init__(self, queue: FakeQueue):
        self._queue = queue
        self.prefetch: int | None = None

    async def set_qos(self, prefetch_count: int) -> None:
        self.prefetch = prefetch_count      # тест проверит, что qos выставлен

    async def get_queue(self, name: str) -> FakeQueue:
        return self._queue


class FakeRabbit:
    """Заглушка RabbitConnection для тестов жизненного цикла воркера.

    Даёт channel с нужным интерфейсом и хуки для теста: deliver сообщения,
    инспекция ack/reject, ожидание старта потребления.
    """

    def __init__(self):
        self._queue = FakeQueue()
        self.channel = FakeChannel(self._queue)
        self._delivered: list = []

    # --- то, что использует воркер ---
    async def close(self) -> None:
        pass

    # --- хуки для теста ---
    def deliver(self, message) -> None:
        self._delivered.append(message)
        self._queue._channel_q.put_nowait(message)

    async def wait_consuming(self) -> None:
        # дождаться, что queue.iterator() реально вошёл в потребление
        await self._queue._consuming.wait()

    def is_acked(self, task_id: str) -> bool:
        return any(m.acked for m in self._delivered if _id_of(m) == task_id)

    def unacked_count(self) -> int:
        return sum(1 for m in self._delivered if not (m.acked or m.rejected))

    def ack_happened_after_db_write(self, task_id: str) -> bool:
        # порядок проверяется по ack_ts из FakeIncomingMessage против метки записи статуса
        msg = next(m for m in self._delivered if _id_of(m) == task_id)
        return msg.acked and msg.ack_ts is not None


def _id_of(message) -> str:
    import json
    return json.loads(message.body)["task_id"]