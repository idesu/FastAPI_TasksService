FROM python:3.11-slim AS builder

WORKDIR /app

# Устанавливаем Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Копируем только файлы зависимостей (для кэширования слоёв)
COPY pyproject.toml poetry.lock* ./

# Настраиваем Poetry: не создавать виртуальное окружение внутри контейнера
RUN poetry config virtualenvs.create false

# Устанавливаем зависимости
RUN poetry install --no-interaction --no-ansi

COPY . .

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]