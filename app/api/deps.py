from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.repositories.task_repository import TaskRepository
from app.rmq_queue.connection import rabbit
from app.rmq_queue.publisher import Publisher, RabbitPublisher
from app.services.task_service import TaskService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


def get_publisher() -> Publisher:
    return RabbitPublisher(rabbit, settings.task_queue)


RepoDep = Annotated[TaskRepository, Depends(get_task_repository)]
PublisherDep = Annotated[Publisher, Depends(get_publisher)]


def get_task_service(
    session: SessionDep,
    repo: RepoDep,
    publisher: PublisherDep,
) -> TaskService:
    return TaskService(session=session, repo=repo, publisher=publisher)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
