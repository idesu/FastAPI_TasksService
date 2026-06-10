from uuid import UUID
from fastapi import APIRouter, Query, status

from app.api.deps import TaskServiceDep
from app.schemas.task import TaskCreate, TaskRead, TaskStatusRead, TaskFilter
from app.models.task import TaskStatus, TaskPriority

router = APIRouter(tags=["tasks"])


@router.post(
    "/tasks",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskRead,
)
async def create_task(payload: TaskCreate, service: TaskServiceDep) -> TaskRead:
    # вся логика в сервисе: task + outbox одной транзакцией, статус NEW
    return await service.create_task(payload)


@router.get("/tasks", response_model=list[TaskRead])
async def list_tasks(
    service: TaskServiceDep,
    status_: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),   # потолок -> не отдаём всю таблицу
    offset: int = Query(default=0, ge=0),
) -> list[TaskRead]:
    flt = TaskFilter(status=status_, priority=priority)
    return await service.list_tasks(flt, limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: UUID, service: TaskServiceDep) -> TaskRead:
    # нет задачи -> сервис кидает TaskNotFound -> хендлер мапит в 404
    return await service.get_task(task_id)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK, response_model=TaskRead)
async def cancel_task(task_id: UUID, service: TaskServiceDep) -> TaskRead:
    # отмена завершённой -> InvalidStatusTransition -> 409, не 500
    return await service.cancel_task(task_id)


@router.get("/tasks/{task_id}/status", response_model=TaskStatusRead)
async def get_task_status(task_id: UUID, service: TaskServiceDep) -> TaskStatusRead:
    # лёгкий эндпоинт под поллинг статуса — отдаёт только статус, не весь объект
    return await service.get_status(task_id)