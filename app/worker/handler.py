import asyncio
import json
import logging
import socket
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.task_repository import TaskRepository
from app.models.task import TaskStatus
from sqlalchemy import update, func
from app.models.task import Task

logger = logging.getLogger(__name__)
WORKER_ID = socket.gethostname()


class TaskHandler:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = TaskRepository(session)

    async def handle(self, body: str) -> None:
        """
        Атомарный claim через UPDATE ... WHERE status = PENDING ... RETURNING.
        Если два воркера получили одно сообщение, забрать задачу сможет только один: апдейт сматчит строку лишь
        пока она PENDING, второй получит ноль строк и тихо выйдет.
        Это защита от двойной обработки без явных блокировок и SELECT FOR UPDATE.
        Источник истины по гонке - база, а не очередь.
        """
        task_id = UUID(json.loads(body)["task_id"])

        # атомарно забираем задачу: PENDING -> IN_PROGRESS
        claimed = await self._repo.claim(task_id, WORKER_ID)
        await self._session.commit()
        if not claimed:
            # уже взята другим воркером или отменена — выходим тихо
            logger.info("task %s already claimed or not pending", task_id)
            return

        try:
            result = await self._process(task_id)
            await self._finish(task_id, TaskStatus.COMPLETED, result=result)
        except Exception as exc:
            logger.exception("task %s failed", task_id)
            await self._finish(task_id, TaskStatus.FAILED, error=str(exc))

    async def _process(self, task_id: UUID) -> dict:
        # здесь полезная работа; для тестового — имитация
        await asyncio.sleep(1)
        return {"ok": True}

    async def _finish(self, task_id, status, *, result=None, error=None) -> None:
        stmt = (
            update(Task).where(Task.id == task_id)
            .values(status=status, finished_at=func.now(),
                    result=result, error=error)
        )
        await self._session.execute(stmt)
        await self._session.commit()