from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.task_repository import TaskRepository
from app.repositories.outbox_repository import OutboxRepository
from app.services.task_service import TaskService


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


def get_outbox_repository(session: SessionDep) -> OutboxRepository:
    return OutboxRepository(session)


TaskRepositoryDep = Annotated[TaskRepository, Depends(get_task_repository)]
OutboxRepositoryDep = Annotated[OutboxRepository, Depends(get_outbox_repository)]


def get_task_service(
    session: SessionDep,
    repo: TaskRepositoryDep,
    outbox: OutboxRepositoryDep,
) -> TaskService:
    return TaskService(session=session, repo=repo, outbox=outbox)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]