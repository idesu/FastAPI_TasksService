import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import String, Text, DateTime, Enum as SAEnum, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class TaskStatus(str, Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Task(Base):
    """
    """
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status"),
        default=TaskStatus.NEW, nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority, name="task_priority"),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(64))

    # частичный индекс под разбор очереди: только то, что ждёт обработки
    # Воркер выбирает только PENDING-задачи, и индекс покрывает ровно их.
    # Он компактный, не раздувается завершёнными задачами, и под высокую нагрузку
    # это заметно дешевле, чем полный индекс по статусу.
    __table_args__ = (
        Index(
            "ix_tasks_pending_queue",
            "priority", "created_at",
            postgresql_where=(status == TaskStatus.PENDING),
        ),
    )