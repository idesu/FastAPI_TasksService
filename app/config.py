from functools import lru_cache
from pydantic import PostgresDsn, AmqpDsn, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # app
    app_name: str = "task-service"
    debug: bool = False

    # postgres
    database_url: PostgresDsn
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # rabbitmq
    rabbitmq_url: AmqpDsn
    task_queue: str = "tasks"
    worker_prefetch: int = Field(default=10, ge=1)

    # worker shutdown
    shutdown_timeout: int = Field(default=30, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()