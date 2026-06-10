from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.repositories.task_repository import TaskRepository
from app.services.task_service import TaskService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


RepoDep = Annotated[TaskRepository, Depends(get_task_repository)]


def get_task_service(session: SessionDep, repo: RepoDep) -> TaskService:
    return TaskService(session=session, repo=repo)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]