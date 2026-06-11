import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy import select

from app.models.outbox import OutboxMessage
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.task import TaskCreate
from app.services.task_service import TaskService
from app.models.task import TaskStatus, Task, TaskPriority
from app.api.errors import InvalidStatusTransition, TaskNotFound


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(session, repo):
    return TaskService(session=session, repo=repo, outbox=repo)


@pytest.mark.asyncio
async def test_cancel_completed_task_raises(service, repo):
    task = AsyncMock(status=TaskStatus.COMPLETED)
    repo.get.return_value = task
    # из COMPLETED отмена запрещена -> доменное исключение
    with pytest.raises(InvalidStatusTransition):
        await service.cancel_task(uuid4())


@pytest.mark.asyncio
async def test_get_missing_task_raises(service, repo):
    repo.get.return_value = None
    with pytest.raises(TaskNotFound):
        await service.get_task(uuid4())


@pytest.mark.asyncio
async def test_create_task_writes_task_and_outbox(db_session):
    service = TaskService(
        session=db_session,
        repo=TaskRepository(db_session),
        outbox=OutboxRepository(db_session),
    )
    result = await service.create_task(TaskCreate(title="t", priority="HIGH"))

    assert result.status == TaskStatus.NEW
    assert result.created_at is not None

    task = await db_session.get(Task, result.id)
    assert task.status == TaskStatus.NEW

    rows = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert len(rows) == 1
    assert rows[0].sent_at is None