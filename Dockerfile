FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/alembic /app/backend/alembic

RUN pip install --no-cache-dir /app/backend

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend/src

EXPOSE 8000

CMD ["uvicorn", "prospectiq.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
