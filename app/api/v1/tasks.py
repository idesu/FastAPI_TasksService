from uuid import UUID
from fastapi import APIRouter, status, Query
from app.api.deps import TaskServiceDep
from app.schemas.task import TaskCreate, TaskRead, TaskStatusRead, TaskList
from app.models.task import TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(payload: TaskCreate, service: TaskServiceDep) -> TaskRead:
    task = await service.create_task(payload)
    return TaskRead.model_validate(task)


@router.get("", response_model=TaskList)
async def list_tasks(
    service: TaskServiceDep,
    status_filter: TaskStatus | None = Query(default=None, alias="status"), # конфликтует с импортом из FastAPI
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TaskList:
    items, total = await service.list_tasks(status_filter, limit, offset)
    return TaskList(
        items=[TaskRead.model_validate(t) for t in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: UUID, service: TaskServiceDep) -> TaskRead:
    task = await service.get_task(task_id)   # кинет TaskNotFound -> 404
    return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(task_id: UUID, service: TaskServiceDep) -> None:
    await service.cancel_task(task_id)       # InvalidStatusTransition -> 409


@router.get("/{task_id}/status", response_model=TaskStatusRead)
async def get_task_status(task_id: UUID, service: TaskServiceDep) -> TaskStatusRead:
    """
    Эндпоинт статуса отдаёт лёгкую схему TaskStatusRead — только id, status и времена,
    без description и result.
    Это горячий запрос, клиент его дёргает в поллинге, гонять полную задачу незачем.
    """
    task = await service.get_task(task_id)
    return TaskStatusRead.model_validate(task)