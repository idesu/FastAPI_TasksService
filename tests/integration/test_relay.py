import pytest
from sqlalchemy import select

from app.workers.relay import RelayWorker
from app.models.task import Task, TaskStatus
from app.models.outbox import OutboxMessage


@pytest.mark.asyncio
async def test_relay_promotes_only_after_confirm(bind_session_factory, fake_publisher):
    """Успешный publish -> sent_at проставлен, задача уехала в PENDING."""
    # сид через ту же фабрику, на которую смотрит relay, и РЕАЛЬНЫЙ commit
    async with bind_session_factory() as s:
        task = Task(title="t", status=TaskStatus.NEW)
        s.add(task)
        await s.flush()
        s.add(OutboxMessage(
            aggregate_id=task.id,
            event_type="task.created",
            payload={"task_id": str(task.id)},
        ))
        await s.commit()
        task_id = task.id

    worker = RelayWorker(fake_publisher)
    sent = await worker._relay_batch()
    assert sent == 1                                    # fetch_unsent увидел строку

    # publish прошёл -> запись помечена отправленной, задача продвинута
    async with bind_session_factory() as s:
        task = await s.get(Task, task_id)
        assert task.status == TaskStatus.PENDING
        msg = (await s.execute(select(OutboxMessage))).scalar_one()
        assert msg.sent_at is not None
        assert msg.retry_count == 0                     # успех с первого раза, ретраев нет


    assert len(fake_publisher.published) == 1           # publish реально случился
    assert fake_publisher.published[0]["task_id"] == str(task_id)


@pytest.mark.asyncio
async def test_relay_keeps_unsent_on_publish_failure(bind_session_factory, failing_publisher):
    """Падение publish -> запись остаётся unsent, статус не двигается, retry_count++.

    Инвариант: статус продвигаем ТОЛЬКО после подтверждённой отправки.
    Брокер упал -> состояние НЕ меняем, попытку фиксируем.
    """
    async with bind_session_factory() as s:
        task = Task(title="t", status=TaskStatus.NEW)
        s.add(task)
        await s.flush()
        s.add(OutboxMessage(
            aggregate_id=task.id,
            event_type="task.created",
            payload={"task_id": str(task.id)},
        ))
        await s.commit()
        task_id = task.id

    worker = RelayWorker(failing_publisher)

    processed = await worker._relay_batch()
    assert processed == 1                             # сообщение взято и обработано

    async with bind_session_factory() as s:
        task = await s.get(Task, task_id)
        assert task.status == TaskStatus.NEW          # статус НЕ продвинут
        msg = (await s.execute(select(OutboxMessage))).scalar_one()
        assert msg.sent_at is None                    # НЕ помечена отправленной
        assert msg.retry_count == 1                   # попытка зафиксирована