# Асинхронный сервис управления задачами

Сервис для асинхронной обработки задач с гарантированной доставкой событий, идемпотентностью и повторными
попытками отправки, а также возможностью масштабирования и отказоустойчивости.

## Описание

Сервис через REST API принимает запросы на создание задачи, сохраняет их в базу данных и публикует событие в RabbitMQ через **Outbox
pattern**. Консюмеры обрабатывают эти задачи и меняют их статус в базе. Неудачные сообщения попадают в **Dead Letter Queue (DLQ)**.

## Технологии

- **FastAPI** + **Pydantic v2** – веб-фреймворк
- **SQLAlchemy 2.0** (async) – ORM
- **PostgreSQL** – база данных
- **RabbitMQ** – брокер сообщений (aio_pika)
- **Alembic** – миграции
- **Docker** + **docker-compose** – контейнеризация


    task-service/
    ├── app/
    │   ├── main.py                      # FastAPI: сборка app, lifespan, роутеры
    │   ├── config.py                    # pydantic-settings: DSN, очереди, таймауты
    │   │
    │   ├── api/
    │   │   ├── deps.py                  # composition root: сессия, репозитории, publisher
    │   │   ├── errors.py                # маппинг доменных исключений в HTTP-коды
    │   │   └── v1/
    │   │       └── tasks.py             # POST/GET/DELETE /api/v1/tasks
    │   │
    │   ├── schemas/
    │   │   └── task.py                  # Pydantic: TaskCreate, TaskRead, фильтры
    │   │
    │   ├── models/
    │   │   ├── base.py                  # DeclarativeBase, общие миксины (timestamps)
    │   │   ├── task.py                  # Task, TaskStatus
    │   │   └── outbox.py                # OutboxMessage
    │   │
    │   ├── repositories/
    │   │   ├── task_repository.py       # add, claim (с reclaim), list, get
    │   │   └── outbox_repository.py     # add, fetch_unsent, mark_sent
    │   │
    │   ├── services/
    │   │   ├── task_service.py          # create_task (task + outbox в одной транзакции)
    │   │   └── exceptions.py            # TaskNotFound, InvalidStatusTransition
    │   │
    │   ├── queue/
    │   │   ├── connection.py            # RabbitConnection, lifecycle коннекта
    │   │   └── publisher.py             # Protocol Publisher + RabbitPublisher
    │   │
    │   ├── db/
    │   │   └── session.py               # async engine, sessionmaker, get_session
    │   │
    │   └── workers/
    │       ├── base.py                  # Worker: graceful shutdown, stop-event, drain
    │       ├── relay.py                 # outbox -> rabbit, NEW -> PENDING
    │       └── task_worker.py           # consume, claim, _process, COMPLETED/FAILED
    │
    ├── migrations/
    │   ├── env.py                       # Alembic, URL из settings
    │   └── versions/
    │
    ├── tests/
    │   ├── conftest.py                  # engine, factory, session (откат), client
    │   ├── unit/                        # сервис с моками репо и publisher
    │   └── integration/                 # реальный Postgres: claim, outbox, SKIP LOCKED
    │
    ├── pyproject.toml
    ├── alembic.ini
    ├── Dockerfile
    ├── docker-compose.yml               # postgres + rabbitmq для локалки
    ├── docker-compose.test.yml          # postgres для тестов


## Запуск

1. Убедитесь, что установлены **Docker** и **docker-compose**.
2. Склонируйте репозиторий и запустите все сервисы:
   ```bash
   git clone <repo-url>
   cd payment-service

   docker-compose up --build
   ```

После запуска будут доступны:
   - API сервис – http://localhost:8000/docs

   - RabbitMQ Management – http://localhost:15672 (guest/guest)

   - PostgreSQL – localhost:5432 (postgres/postgres)

## Архитектура

Чистое разделение: роутеры — транспорт, сервис — бизнес-логика, репозиторий — доступ к данным.
Репозиторий ничего не знает про commit, только add, flush, select. Границу транзакции держит сервис — это Unit of Work.
Сессия инжектится в сервис явной зависимостью.

DI и инверсия зависимостей. Всё, что ходит во внешний мир — сессия, репозиторий, publisher — инжектится в конструктор,
а не импортируется жёстко. Publisher завязан на Protocol-интерфейс, не на конкретный RabbitPublisher.
Создание конкретных реализаций стянуто в один composition root — deps.py.

Воркер и защита от двойной обработки. Надёжность строится на атомарном claim через `UPDATE ... WHERE status = PENDING ... RETURNING`.
Два воркера получили одно сообщение — забрать сможет только один, второй получит ноль строк и тихо выйдет.
Источник истины при гонке - база, а не очередь. Это даёт идемпотентность поверх at-least-once доставки RabbitMQ.
requeue=False уводит ядовитые сообщения в DLQ вместо зацикливания.

Graceful shutdown. Воркер в классе Worker со стоп-эвентом и трекингом in-flight задач.
По SIGTERM от Kubernetes: сначала queue.cancel — перестаю забирать новые, потом drain уже запущенных через asyncio.wait
с таймаутом, потом закрываю коннект. Кого не успел забрать — cancel, сообщения без ack вернутся в очередь,
потери нет за счёт at-least-once и claim.


### Возможные улучшения

- Расширить логирование.
- Реализовать обработку DLQ (например, отдельный consumer для повторной обработки).
- Больше тестов.
- CI, коммит хуки
