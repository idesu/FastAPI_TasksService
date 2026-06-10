import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.healthchecks import check_database, check_rabbitmq
from app.api.v1 import tasks
from app.config import settings
from app.db.session import dispose_engine
from app.rmq_queue.connection import RabbitConnection
from app.api.errors import TaskNotFound, InvalidStatusTransition, register_exception_handlers

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    app.state.rabbit = await RabbitConnection.connect()   # один коннект на процесс
    yield
    await app.state.rabbit.close()
    await dispose_engine()


app = FastAPI(
    title="Task Service",
    version="1.0.0",
    lifespan=lifespan,
)
register_exception_handlers(app)

app.include_router(tasks.router, prefix="/api/v1")


@app.exception_handler(TaskNotFound)
async def task_not_found_handler(request: Request, exc: TaskNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidStatusTransition)
async def invalid_transition_handler(request: Request, exc: InvalidStatusTransition):
    # бизнес-ошибка перехода статуса -> 409, не 500
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health/live", include_in_schema=False)
async def liveness() -> dict:
    # процесс жив — никаких внешних пингов, иначе k8s убьёт под при моргании БД
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def readiness() -> dict:
    # готов принимать трафик — здесь уместны реальные пинги зависимостей
    rabbit_ok = not app.state.rabbit.channel.is_closed
    return {"status": "ok" if rabbit_ok else "degraded"}
