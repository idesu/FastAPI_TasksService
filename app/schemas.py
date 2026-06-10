from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from app.models import TaskPriority, TaskStatus

class TaskCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM

class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: str | None
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: str | None
    error_info: str | None

class TaskStatusResponse(BaseModel):
    id: UUID
    status: TaskStatus

class TaskListParams(BaseModel):
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    limit: int = Field(10, ge=1, le=100)
    offset: int = Field(0, ge=0)