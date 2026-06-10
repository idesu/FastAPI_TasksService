from uuid import UUID
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task, TaskStatus


class TaskRepository:
    """
    Репозиторий делает flush, не commit, бизнес-логики в нём нет, атомарный claim тут как операция доступа к данным.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()   # получаем id, но не коммитим
        return task

    async def get(self, task_id: UUID) -> Task | None:
        return await self._session.get(Task, task_id)

    async def list(
        self, status: TaskStatus | None, limit: int, offset: int
    ) -> list[Task]:
        stmt = select(Task)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        stmt = (
            stmt.order_by(Task.priority.desc(), Task.created_at)
            .limit(limit).offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: TaskStatus | None) -> int:
        stmt = select(func.count()).select_from(Task)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def claim(self, task_id: UUID, worker_id: str) -> bool:
        stmt = (
            update(Task)
            .where(Task.id == task_id, Task.status == TaskStatus.PENDING)
            .values(status=TaskStatus.IN_PROGRESS,
                    started_at=func.now(), worker_id=worker_id)
            .returning(Task.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None