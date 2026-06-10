#!/bin/bash
set -e

echo "Starting test database..."
docker-compose -f docker-compose.tests.yml up -d test-db

# Ждём, пока БД будет готова
echo "Waiting for PostgreSQL to be ready..."
until docker-compose -f docker-compose.tests.yml exec -T test-db pg_isready -U test_user; do
  sleep 1
done

echo "Running tests..."
poetry run pytest tests/ -v --cov=app --cov-report=term-missing

# Останавливаем контейнер
echo "Stopping test database..."
docker-compose -f docker-compose.tests.yml down -v