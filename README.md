    task-service/
    ├── app/
    │   ├── main.py                  # сборка FastAPI, роутеры, lifespan
    │   ├── config.py                # Settings через pydantic-settings, всё из env
    │   │
    │   ├── api/                     # HTTP-слой, тонкий
    │   │   ├── deps.py              # Depends: сессия, репозиторий, сервис
    │   │   ├── errors.py            # exception handlers, маппинг на HTTP-коды
    │   │   └── v1/
    │   │       ├── router.py        # сборка роутеров v1
    │   │       └── tasks.py         # эндпоинты /api/v1/tasks
    │   │
    │   ├── schemas/                 # Pydantic: запросы и ответы
    │   │   └── task.py              # TaskCreate, TaskRead, TaskStatusRead
    │   │
    │   ├── services/                # бизнес-логика, переходы статусов
    │   │   └── task_service.py      # create, cancel, валидация переходов
    │   │
    │   ├── repositories/            # доступ к данным, SQLAlchemy
    │   │   └── task_repository.py
    │   │
    │   ├── models/                  # ORM-модели, enum'ы
    │   │   ├── base.py
    │   │   └── task.py
    │   │
    │   ├── db/                      # подключение к БД
    │   │   ├── engine.py            # async engine, sessionmaker
    │   │   └── session.py           # get_session
    │   │
    │   ├── queue/                   # работа с RabbitMQ
    │   │   ├── publisher.py         # публикация задачи в очередь
    │   │   └── connection.py
    │   │
    │   └── worker/                  # отдельный процесс-потребитель
    │       ├── consumer.py          # читает очередь, вызывает handler
    │       └── handler.py           # claim задачи, обработка, статус
    │
    ├── migrations/                  # Alembic
    │   ├── env.py
    │   └── versions/
    │
    ├── tests/
    │   ├── conftest.py              # фикстуры: тестовая БД, моки очереди
    │   ├── unit/                    # сервис с замоканным репозиторием
    │   └── integration/             # API + БД через testcontainers
    │
    ├── Dockerfile
    ├── docker-compose.yml           # сервис, воркер, postgres, rabbitmq
    ├── alembic.ini
    ├── pyproject.toml
    └── .env.example


Главное — api и worker это две точки входа в один кодген. Веб-сервис и воркер запускаются как разные процессы, но переиспользуют общие слои: модели, репозиторий, конфиг, подключение к БД. Дублирования нет, масштабирую их независимо.

Слой schemas отделён от models намеренно. Pydantic-схемы — это контракт API, ORM-модели — это хранение. Их нельзя смешивать: иначе детали БД утекают в API, и любое изменение таблицы ломает контракт.

config.py один на всё, читает только из переменных окружения через pydantic-settings. Это закрывает требование про конфигурацию через env и даёт валидацию настроек на старте — сервис падает сразу, если переменной нет, а не в рантайме.

errors.py с глобальными exception handlers — доменные исключения сервиса маплю на HTTP-коды в одном месте. Сервис кидает TaskNotFound или InvalidTransition, а слой api превращает это в 404 или 409. Бизнес-логика не знает про HTTP.

Тесты разделены на unit и integration осознанно. Unit гоняют сервис с замоканным репозиторием — быстро, без БД. Integration поднимают реальный Postgres через testcontainers и проверяют связку целиком. Это прямо отвечает на критерий про покрытие тестами.

Чего сознательно не усложняю. Не ввожу отдельный domain-слой с чистыми сущностями и мапперами — для такого объёма ORM-модели как доменные сущности достаточно. Гексагональную архитектуру с портами и адаптерами здесь городить не стал бы: это оправдано на большой системе с несколькими источниками данных, а тут один Postgres и одна очередь. Архитектуру держу ровно под размер задачи.
