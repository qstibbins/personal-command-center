.PHONY: infra-up infra-down api web worker test migrate
infra-up:
	docker compose up -d
infra-down:
	docker compose down
api:
	cd apps/api && uv run uvicorn pcc.main:app --reload --host 127.0.0.1 --port 8000
web:
	pnpm dev:web
worker:
	cd apps/api && uv run python -m pcc.worker.main
test:
	cd apps/api && uv run pytest
migrate:
	cd apps/api && uv run alembic upgrade head
