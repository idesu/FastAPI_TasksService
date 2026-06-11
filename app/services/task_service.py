import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.task_repository import TaskRepository
from app.repositories.outbox_repository import OutboxRepository
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskRead, TaskStatusRead, TaskFilter
from app.services.exceptions import TaskNotFound, InvalidStatusTransition

logger = logging.getLogger(__name__)

_CANCELLABLE = {TaskStatus.NEW, TaskStatus.PENDING}


class TaskService:
    def __init__(
        self,
        session: AsyncSession,
        repo: TaskRepository,
        outbox: OutboxRepository,
    ):
        self._session = session       # сервис держит границу транзакции
        self._repo = repo
        self._outbox = outbox

    async def create_task(self, payload: TaskCreate) -> TaskRead:
        task = Task(
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            status=TaskStatus.NEW,        # NEW -> PENDING relay переведёт в после publish
        )
        await self._repo.add(task)        # flush внутри -> появляется task.id

        # задача и событие пишутся в ОДНОЙ транзакции
        await self._outbox.add(
            aggregate_id=task.id,
            event_type="task.created",
            payload={"task_id": str(task.id), "priority": task.priority.value},
        )

        await self._session.commit()      # атомарно: либо обе записи, либо ни одной
        return TaskRead.model_validate(task)

    async def get_task(self, task_id: UUID) -> TaskRead:
        task = await self._repo.get(task_id)
        if task is None:
            raise TaskNotFound(f"task {task_id} not found")
        return TaskRead.model_validate(task)

    async def get_status(self, task_id: UUID) -> TaskStatusRead:
        task = await self._repo.get(task_id)
        if task is None:
            raise TaskNotFound(f"task {task_id} not found")
        return TaskStatusRead.model_validate(task)

    async def list_tasks(self, flt: TaskFilter, limit: int, offset: int) -> list[TaskRead]:
        tasks = await self._repo.list(flt, limit=limit, offset=offset)
        return [TaskRead.model_validate(t) for t in tasks]

    async def cancel_task(self, task_id: UUID) -> TaskRead:
        task = await self._repo.get(task_id)
        if task is None:
            raise TaskNotFound(f"task {task_id} not found")

        # бизнес-правило: завершённую/выполняющуюся задачу не отменяем
        if task.status not in _CANCELLABLE:
            raise InvalidStatusTransition(
                f"cannot cancel task in status {task.status.value}"
            )

        task.status = TaskStatus.CANCELLED
        await self._session.commit()
        return TaskRead.model_validate(task)