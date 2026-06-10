import asyncio
import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.models.task import Task, TaskStatus
from app.repositories.task_repository import TaskRepository


@pytest.mark.asyncio
async def test_concurrent_claim_only_one_wins(engine):
    task_id = uuid4()
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with factory() as s:
        s.add(Task(id=task_id, title="t", priority="LOW", status=TaskStatus.PENDING))
        await s.commit()

    async def claim(worker: str) -> bool:
        # каждый воркер в своей сессии, как в реальном проде
        async with factory() as s:
            ok = await TaskRepository(s).claim(task_id, worker)
            await s.commit()
            return ok

    # два воркера дерутся за одну задачу одновременно
    results = await asyncio.gather(claim("w1"), claim("w2"))
    assert sum(results) == 1   # ровно один забрал, второй получил False