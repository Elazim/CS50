.PHONY: setup infra-up infra-down migrate api worker web dev test lint typecheck client openapi

## One-time setup: python venv + js workspace
setup:
	cd apps/api && uv venv .venv && uv pip install -e ".[dev]"
	pnpm install

## Start dev dependencies (postgres, redis, minio)
infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd apps/api && .venv/bin/alembic upgrade head

api:
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000 --app-dir src

worker:
	cd apps/api && .venv/bin/celery -A app.worker.celery_app:celery_app worker --loglevel=info

web:
	pnpm --filter web dev

test:
	cd apps/api && .venv/bin/pytest -q

lint:
	cd apps/api && .venv/bin/ruff check src tests evals

corpus:
	cd apps/api && PYTHONPATH=src:. .venv/bin/python scripts/build_corpus.py

typecheck:
	cd apps/api && .venv/bin/mypy src
	pnpm --filter web typecheck

## Regenerate the OpenAPI schema and the TypeScript client from it
openapi:
	cd apps/api && PYTHONPATH=src .venv/bin/python scripts/export_openapi.py > ../../packages/schemas/openapi.json

client: openapi
	pnpm client:generate
