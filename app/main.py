from fastapi import FastAPI
from app.api.v1.tasks import router

app = FastAPI(title="Task Service", version="1.0")

app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok"}