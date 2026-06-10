
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.database import get_db
from app.services.task_service import TaskService
from app.services.rabbitmq import publish_task
from app.schemas import TaskCreate, TaskResponse, TaskStatusResponse, TaskListParams
from app.models import TaskStatus

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task_data: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = await TaskService.create_task(db, task_data)
    # Отправляем в очередь (статус становится PENDING)
    await TaskService.update_task_status(db, task.id, TaskStatus.PENDING)
    await publish_task(task.id, task.priority.value)
    return task

@router.get("/", response_model=list[TaskResponse])
async def get_tasks(params: TaskListParams = Depends(), db: AsyncSession = Depends(get_db)):
    tasks = await TaskService.get_tasks(db, params.status, params.priority, params.limit, params.offset)
    return tasks

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.delete("/{task_id}", response_model=TaskResponse)
async def cancel_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await TaskService.cancel_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(id=task.id, status=task.status)