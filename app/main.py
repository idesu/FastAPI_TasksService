import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.healthchecks import check_database, check_rabbitmq
from app.api.v1 import tasks
from app.config import settings
from app.rmq_queue.connection import rabbit
from app.db.engine import engine
from app.api.errors import TaskNotFound, InvalidStatusTransition

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # старт: поднимаем коннект к брокеру один раз на процесс
    await rabbit.connect()
    yield
    # стоп: корректно отпускаем ресурсы
    await rabbit.close()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(tasks.router, prefix="/api/v1")


@app.exception_handler(TaskNotFound)
async def task_not_found_handler(request: Request, exc: TaskNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidStatusTransition)
async def invalid_transition_handler(request: Request, exc: InvalidStatusTransition):
    # бизнес-ошибка перехода статуса -> 409, не 500
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict:
    db_ok = await check_database()
    rabbit_ok = await check_rabbitmq()
    status = "healthy" if (db_ok and rabbit_ok) else "unhealthy"
    return {
        "status": status,
        "database": "up" if db_ok else "down",
        "rabbitmq": "up" if rabbit_ok else "down",
    }
