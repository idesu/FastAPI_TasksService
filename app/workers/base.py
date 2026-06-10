import asyncio
import logging
import signal

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, shutdown_timeout: float = 25.0):
        self._stop = asyncio.Event()
        self._shutdown_timeout = shutdown_timeout
        self._in_flight: set[asyncio.Task] = set()

    def _install_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop.set)   # SIGTERM от k8s -> мягкий стоп

    def _track(self, coro) -> None:
        # держим ссылку на in-flight задачу, чтобы дождаться её при shutdown
        task = asyncio.create_task(coro)
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)

    async def _drain(self) -> None:
        if not self._in_flight:
            return
        logger.info("draining %d in-flight tasks", len(self._in_flight))
        done, pending = await asyncio.wait(
            self._in_flight, timeout=self._shutdown_timeout
        )
        for t in pending:
            t.cancel()   # не успели за таймаут -> отменяем, сообщение вернётся в очередь

    async def run(self) -> None:
        #self._install_signals()
        try:
            await self._loop()        # реализуется в наследнике
        finally:
            await self._drain()
            await self._cleanup()     # закрыть коннекты

    async def _loop(self) -> None:
        raise NotImplementedError

    async def _cleanup(self) -> None:
        pass