from uuid import UUID
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxMessage


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, aggregate_id: UUID, event_type: str, payload: dict) -> None:
        # вызывается сервисом в той же транзакции, что и Task; commit делает сервис
        self._session.add(
            OutboxMessage(
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
            )
        )

    async def fetch_unsent(self, limit: int) -> list[OutboxMessage]:
        # читается relay; SKIP LOCKED -> несколько relay не дерутся за одни строки
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.sent_at.is_(None))   # частичный индекс ix_outbox_unsent
            .order_by(OutboxMessage.created_at)        # FIFO по времени создания
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def mark_sent(self, message_id: UUID) -> None:
        # relay проставляет sent_at после успешного publish + confirm
        await self._session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(sent_at=func.now())
        )

    async def mark_failed(self, message_id: UUID) -> None:
        # publish упал -> инкремент retry_count, sent_at НЕ трогаем -> подхватится снова
        await self._session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(retry_count=OutboxMessage.retry_count + 1)
        )