from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.task import TaskStatus, TaskPriority


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: dict | None
    error: str | None


class TaskStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: TaskStatus
    started_at: datetime | None
    finished_at: datetime | None


class TaskList(BaseModel):
    items: list[TaskRead]
    total: int
    limit: int
    offset: int