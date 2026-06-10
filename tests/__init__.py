import pytest
from httpx import AsyncClient
from app.main import app
from app.database import get_db
from app.models import TaskStatus, TaskPriority

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_task(client):
    response = await client.post("/api/v1/tasks/", json={
        "title": "Test task",
        "description": "desc",
        "priority": "HIGH"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test task"
    assert data["status"] == "NEW"

@pytest.mark.asyncio
async def test_get_task(client):
    # Сначала создадим
    create_resp = await client.post("/api/v1/tasks/", json={"title": "Get me"})
    task_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["id"] == task_id