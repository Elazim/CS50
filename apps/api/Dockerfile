FROM python:3.12-slim AS base

WORKDIR /srv/api
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md* ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

EXPOSE 8000

# API by default; the worker deployment overrides the command:
#   celery -A app.worker.celery_app:celery_app worker --loglevel=info
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
