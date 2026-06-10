from uuid import UUID
from sqlalchemy import select, update, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus
from app.schemas.task import TaskFilter

# таймаут, после которого IN_PROGRESS считается зависшим (мёртвый воркер)
_STUCK_INTERVAL = text("interval '5 minutes'")


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()   # нужен id; commit делает сервис
        return task

    async def get(self, task_id: UUID) -> Task | None:
        return await self._session.get(Task, task_id)

    async def list(self, flt: TaskFilter, limit: int, offset: int) -> list[Task]:
        stmt = select(Task)
        if flt.status is not None:
            stmt = stmt.where(Task.status == flt.status)
        if flt.priority is not None:
            stmt = stmt.where(Task.priority == flt.priority)
        # стабильный порядок для пагинации — иначе offset скачет
        stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        return list((await self._session.execute(stmt)).scalars().all())

    async def claim(self, task_id: UUID, worker_id: str) -> bool:
        """Атомарно забрать задачу: PENDING или зависший IN_PROGRESS -> IN_PROGRESS."""
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                or_(
                    Task.status == TaskStatus.PENDING,
                    # reclaim: воркер умер, started_at протух -> переотдаём
                    and_(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.started_at < func.now() - _STUCK_INTERVAL,
                    ),
                ),
            )
            .values(
                status=TaskStatus.IN_PROGRESS,
                worker_id=worker_id,
                started_at=func.now(),
            )
            .returning(Task.id)
        )
        result = await self._session.execute(stmt)
        # ноль строк -> уже взято другим воркером; не дубль
        return result.scalar_one_or_none() is not None

    async def heartbeat(self, task_id: UUID, worker_id: str) -> None:
        # живой воркер двигает started_at, чтобы долгую задачу не переотдали как зависшую
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id,
                    Task.worker_id == worker_id,
                    Task.status == TaskStatus.IN_PROGRESS,
                   )
            .values(started_at=func.now())
        )

    async def set_final_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status=status,
                result=result,
                error=error,
                finished_at=func.now(),
            )
        )