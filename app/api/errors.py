from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """База для доменных ошибок."""


class TaskNotFound(DomainError):
    pass


class InvalidStatusTransition(DomainError):
    pass


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TaskNotFound)
    async def _not_found(request: Request, exc: TaskNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidStatusTransition)
    async def _conflict(request: Request, exc: InvalidStatusTransition):
        return JSONResponse(status_code=409, content={"detail": str(exc)})
