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


Главное — api и worker это две точки входа в один кодген. Веб-сервис и воркер запускаются как разные процессы, но переиспользуют общие слои: модели, репозиторий, конфиг, подключение к БД. Дублирования нет, масштабирую их независимо.

Слой schemas отделён от models намеренно. Pydantic-схемы — это контракт API, ORM-модели — это хранение. Их нельзя смешивать: иначе детали БД утекают в API, и любое изменение таблицы ломает контракт.

config.py один на всё, читает только из переменных окружения через pydantic-settings. Это закрывает требование про конфигурацию через env и даёт валидацию настроек на старте — сервис падает сразу, если переменной нет, а не в рантайме.

errors.py с глобальными exception handlers — доменные исключения сервиса маплю на HTTP-коды в одном месте. Сервис кидает TaskNotFound или InvalidTransition, а слой api превращает это в 404 или 409. Бизнес-логика не знает про HTTP.

Тесты разделены на unit и integration осознанно. Unit гоняют сервис с замоканным репозиторием — быстро, без БД. Integration поднимают реальный Postgres через testcontainers и проверяют связку целиком. Это прямо отвечает на критерий про покрытие тестами.

Чего сознательно не усложняю. Не ввожу отдельный domain-слой с чистыми сущностями и мапперами — для такого объёма ORM-модели как доменные сущности достаточно. Гексагональную архитектуру с портами и адаптерами здесь городить не стал бы: это оправдано на большой системе с несколькими источниками данных, а тут один Postgres и одна очередь. Архитектуру держу ровно под размер задачи.


Сервис обработки задач на FastAPI плюс отдельный воркер, общаются через RabbitMQ, состояние в PostgreSQL. Разберу по слоям и ключевым решениям.

Архитектура и слои. Чистое разделение: роутеры — транспорт, сервис — бизнес-логика, репозиторий — доступ к данным. Репозиторий ничего не знает про commit, только add, flush, select. Границу транзакции держит сервис — это Unit of Work. Сессия инжектится в сервис явной зависимостью, не достаётся через приватное поле репозитория.

DI и инверсия зависимостей. Всё, что ходит во внешний мир — сессия, репозиторий, publisher — инжектится в конструктор, а не импортируется жёстко. Publisher завязан на Protocol-интерфейс, не на конкретный RabbitPublisher. Сервис не знает, что под капотом раббит — завтра Kafka, сервис не трогаю. Создание конкретных реализаций стянуто в один composition root — deps.py.

Транзакции и согласованность. Одна сессия на запрос, FastAPI кеширует Depends(get_session), поэтому flush репозитория и commit сервиса — одна транзакция. Publish в очередь идёт строго после commit: иначе словлю сообщение про задачу, которой нет в базе, если транзакция откатится. Полное решение dual write — transactional outbox, назвал бы его как правильный следующий шаг.

Воркер и защита от двойной обработки. Сердце надёжности — атомарный claim через UPDATE ... WHERE status = PENDING ... RETURNING. Два воркера получили одно сообщение — забрать сможет только один, второй получит ноль строк и тихо выйдет. База — источник правды по гонке, не очередь. Это даёт идемпотентность поверх at-least-once доставки RabbitMQ. requeue=False уводит ядовитые сообщения в DLQ вместо зацикливания.

Graceful shutdown. Воркер в классе Worker со стоп-эвентом и трекингом in-flight задач. По SIGTERM от Kubernetes: сначала queue.cancel — перестаю забирать новые, потом drain уже запущенных через asyncio.wait с таймаутом, потом закрываю коннект. shutdown_timeout держу меньше terminationGracePeriodSeconds. Кого не успел — cancel, сообщения без ack вернутся в очередь, потери нет за счёт at-least-once и claim.

Конфигурация и жизненный цикл. Настройки через pydantic-settings, типизированные DSN — кривой URL роняет приложение на старте, а не в проде на первом запросе. lifespan поднимает коннект к брокеру один раз на процесс. Доменные исключения мапятся в коды: TaskNotFound это 404, InvalidStatusTransition это 409 — сервис чистый от HTTP-специфики.

Миграции. Alembic, URL из того же settings — один источник правды. compare_type и compare_server_default включены. Частичный индекс ix_tasks_pending под claim — индексирую только PENDING, а не завершённые задачи, которых со временем большинство. Для прода — zero-downtime подход и CREATE INDEX CONCURRENTLY.

Тесты. Два уровня с чётким разделением. Юнит на сервисе с замоканным репозиторием и publisher — быстрые, проверяют бизнес-правила. Интеграционные на реальном Postgres — проверяют то, что моками нельзя: атомарность claim под asyncio.gather, SKIP LOCKED распределение строк, откат транзакции при частичном падении, уникальные констрейнты под гонкой. Изоляция через транзакцию с откатом на каждый тест. API end-to-end через httpx.AsyncClient с dependency_overrides. Принцип: на моках тестирую свою логику, на реальной базе — свои предположения о базе.

Сквозная инженерная линия, которую я бы озвучил. Всё держится на трёх вещах. Первое — явные зависимости через DI вместо скрытых импортов, отсюда тестируемость и заменяемость. Второе — база как источник правды по конкуренции: атомарный claim и констрейнты вместо проверок в коде, которые ловят TOCTOU. Третье — корректность под отказами: at-least-once плюс идемпотентность, graceful shutdown под grace period оркестратора, publish после commit. Это не учебный CRUD, а сервис, спроектированный под реальные режимы отказа.