import pytest
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.main import app
from app.models.task import Task, TaskStatus


async def seed_task(
    db_session: AsyncSession,
    *,
    status: TaskStatus = TaskStatus.PENDING,
    **overrides,
) -> Task:
    defaults = dict(id=uuid4(), title="seeded", priority="LOW", status=status)
    task = Task(**{**defaults, **overrides})
    db_session.add(task)
    await db_session.flush()
    return task   # возвращаю объект целиком — нужен и id, и поля для ассертов


@pytest_asyncio.fixture
async def client(db_session):
    # подменяем сессию приложения на тестовую (транзакция с откатом)
    app.dependency_overrides[get_session] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_and_get_task(client):
    resp = await client.post("/api/v1/tasks", json={"title": "t", "priority": "LOW"})
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    got = await client.get(f"/api/v1/tasks/{task_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "NEW"


@pytest.mark.asyncio
async def test_get_missing_returns_404(client):
    resp = await client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404  # TaskNotFound -> 404, не 500


@pytest.mark.asyncio
async def test_cancel_completed_returns_409(client, db_session):
    # готовим задачу сразу в COMPLETED через сессию
    task = await seed_task(db_session, status=TaskStatus.COMPLETED)
    resp = await client.delete(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 409  # InvalidStatusTransition -> 409 Conflict
