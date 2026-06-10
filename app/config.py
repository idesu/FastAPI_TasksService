from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "taskuser"
    POSTGRES_PASSWORD: str = "taskpass"
    POSTGRES_DB: str = "taskdb"

    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    RABBITMQ_QUEUE: str = "tasks_queue"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def rabbitmq_url(self) -> str:
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"

    class Config:
        env_file = ".env"

settings = Settings()