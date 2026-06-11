from uuid import UUID
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxMessage
from app.models.task import Task, TaskStatus


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, aggregate_id: UUID, event_type: str, payload: dict) -> None:
        # вызывается TaskService в ОДНОЙ транзакции с Task; commit делает сервис
        self._session.add(
            OutboxMessage(
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
            )
        )

    async def fetch_unsent(self, limit: int) -> list[OutboxMessage]:
        # читается relay; SKIP LOCKED -> пара relay не дерётся за одни строки
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.sent_at.is_(None))    # бьёт в частичный индекс ix_outbox_unsent
            .order_by(OutboxMessage.created_at)        # FIFO по времени вставки
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def mark_sent_and_promote(self, message_id: UUID, aggregate_id: UUID) -> None:
        """
        ВЫЗЫВАЕТСЯ ТОЛЬКО ПОСЛЕ publisher confirm.
        sent_at и переход NEW -> PENDING фиксируются вместе; commit делает relay.
        """
        await self._session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(sent_at=func.now())
        )
        await self._session.execute(
            update(Task)
            .where(Task.id == aggregate_id, Task.status == TaskStatus.NEW)
            .values(status=TaskStatus.PENDING)   # condition NEW -> идемпотентно, не перетрёт IN_PROGRESS
        )

    async def mark_failed(self, message_id: UUID) -> None:
        # publish упал -> инкремент retry_count, sent_at НЕ трогаем -> подхватится снова
        await self._session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(retry_count=OutboxMessage.retry_count + 1)
        )