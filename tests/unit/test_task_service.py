import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.task_service import TaskService
from app.models.task import TaskStatus
from app.api.errors import InvalidStatusTransition, TaskNotFound


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(session, repo):
    return TaskService(session=session, repo=repo, publisher=AsyncMock())


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
async def test_cancel_pending_commits(service, repo, session):
    task = AsyncMock(status=TaskStatus.PENDING)
    repo.get.return_value = task
    await service.cancel_task(uuid4())
    assert task.status == TaskStatus.CANCELLED
    session.commit.assert_awaited_once()   # транзакция закрыта именно сервисом
