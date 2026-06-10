from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, Enum, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class TaskPriority(PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class TaskStatus(PyEnum):
    NEW = "NEW"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Enum(TaskPriority), nullable=False, default=TaskPriority.MEDIUM)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.NEW)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)
    error_info = Column(Text, nullable=True)