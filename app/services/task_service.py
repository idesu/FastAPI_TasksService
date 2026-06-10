from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task, TaskStatus
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate
from app.rmq_queue.publisher import Publisher
from app.api.errors import TaskNotFound, InvalidStatusTransition

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.NEW: {TaskStatus.PENDING, TaskStatus.CANCELLED},
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}

_PRIORITY_MAP = {"LOW": 1, "MEDIUM": 5, "HIGH": 10}


class TaskService:
    def __init__(self, session: AsyncSession, repo: TaskRepository, publisher: Publisher) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher

    async def create_task(self, payload: TaskCreate) -> Task:
        task = Task(
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            status=TaskStatus.PENDING,
        )
        await self._repo.add(task)        # flush -> есть id, коммита нет
        await self._session.commit()      # транзакцией рулит сервис

        # публикация ПОСЛЕ коммита: в БД задача уже точно есть
        await self._publisher.publish(str(task.id), _PRIORITY_MAP[payload.priority.value])
        return task

    async def get_task(self, task_id: UUID) -> Task:
        task = await self._repo.get(task_id)
        if task is None:
            raise TaskNotFound(f"task {task_id} not found")
        return task

    async def list_tasks(self, status, limit, offset) -> tuple[list[Task], int]:
        items = await self._repo.list(status, limit, offset)
        total = await self._repo.count(status)
        return items, total

    async def cancel_task(self, task_id: UUID) -> Task:
        task = await self.get_task(task_id)
        self._ensure_transition(task.status, TaskStatus.CANCELLED)
        task.status = TaskStatus.CANCELLED
        await self._session.commit()
        return task

    def _ensure_transition(self, current: TaskStatus, target: TaskStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[current]:
            raise InvalidStatusTransition(
                f"cannot move from {current.value} to {target.value}"
            )