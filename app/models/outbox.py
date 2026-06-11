import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="task.created")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # частичный индекс ТОЛЬКО по неотправленным — relay читает по нему
        Index(
            "ix_outbox_unsent",
            "created_at",
            postgresql_where=(sent_at.is_(None)),
        ),
    )