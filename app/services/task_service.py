from uuid import UUID
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Task, TaskStatus, TaskPriority
from app.schemas import TaskCreate

class TaskService:
    @staticmethod
    async def create_task(db: AsyncSession, task_data: TaskCreate) -> Task:
        task = Task(
            title=task_data.title,
            description=task_data.description,
            priority=task_data.priority,
            status=TaskStatus.NEW
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def get_task(db: AsyncSession, task_id: UUID) -> Task | None:
        result = await db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tasks(db: AsyncSession, status: TaskStatus | None, priority: TaskPriority | None, limit: int, offset: int):
        query = select(Task)
        if status:
            query = query.where(Task.status == status)
        if priority:
            query = query.where(Task.priority == priority)
        query = query.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_task_status(db: AsyncSession, task_id: UUID, status: TaskStatus, **kwargs):
        task = await TaskService.get_task(db, task_id)
        if task:
            task.status = status
            for key, value in kwargs.items():
                setattr(task, key, value)
            await db.commit()
            await db.refresh(task)
        return task

    @staticmethod
    async def cancel_task(db: AsyncSession, task_id: UUID) -> Task | None:
        task = await TaskService.get_task(db, task_id)
        if task and task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()
            await db.commit()
            await db.refresh(task)
        return task