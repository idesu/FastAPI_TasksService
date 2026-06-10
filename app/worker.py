import asyncio
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings
from app.models import TaskStatus
from app.services.task_service import TaskService
from app.services.rabbitmq import consume_tasks
from aio_pika import IncomingMessage

engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def process_task(message: IncomingMessage):
    async with message.process():
        data = json.loads(message.body.decode())
        task_id_str = data["task_id"]
        task_id = uuid.UUID(task_id_str)

        async with AsyncSessionLocal() as db:
            task = await TaskService.get_task(db, task_id)
            if not task:
                return

            # Проверка отмены
            if task.status == TaskStatus.CANCELLED:
                return

            # Обновляем статус на IN_PROGRESS
            await TaskService.update_task_status(
                db, task_id, TaskStatus.IN_PROGRESS,
                started_at=datetime.utcnow()
            )

            try:
                # Имитация обработки (заменить на реальную бизнес-логику)
                await asyncio.sleep(2)  # например, долгая операция
                result_text = f"Task '{task.title}' processed successfully."
                await TaskService.update_task_status(
                    db, task_id, TaskStatus.COMPLETED,
                    completed_at=datetime.utcnow(),
                    result=result_text,
                    error_info=None
                )
            except Exception as e:
                await TaskService.update_task_status(
                    db, task_id, TaskStatus.FAILED,
                    completed_at=datetime.utcnow(),
                    error_info=str(e)
                )

async def main():
    await consume_tasks(process_task)

if __name__ == "__main__":
    import uuid
    asyncio.run(main())