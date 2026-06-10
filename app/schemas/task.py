from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.models.task import TaskStatus, TaskPriority


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    priority: TaskPriority = TaskPriority.MEDIUM   # дефолт, если не прислали

    model_config = ConfigDict(extra="forbid")  # лишнее поле -> 422, не молча проглотить


class TaskFilter(BaseModel):
    status: TaskStatus | None = None
    priority: TaskPriority | None = None



class TaskRead(BaseModel):
    id: UUID
    title: str
    description: str | None
    priority: TaskPriority
    status: TaskStatus
    result: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TaskStatusRead(BaseModel):
    id: UUID
    status: TaskStatus
    error: str | None = None

    model_config = ConfigDict(from_attributes=True)