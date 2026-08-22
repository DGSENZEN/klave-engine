.PHONY: install test lint typecheck demo-data ingest-demo convert-demo parse-demo process-demo eval-demo eval-gold gold-capture api web web-install clean users-db-up users-db-down

users-db-up:
	docker compose up -d users-db

users-db-down:
	docker compose stop users-db

users-db-backup:
	@mkdir -p backups
	docker exec klave-users-db pg_dump -U klave_users klave_users \
		> backups/users-$$(date +%Y%m%d-%H%M%S).sql
	@ls -t backups/users-*.sql | head -1

# Restore: docker exec -i klave-users-db psql -U klave_users klave_users < backups/users-<ts>.sql

DEMO_PROJECT := data/demo/demo_project_001

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy packages/klave_engine

demo-data:
	uv run klave demo $(DEMO_PROJECT)

ingest-demo:
	uv run klave ingest $(DEMO_PROJECT)

convert-demo:
	uv run klave convert $(DEMO_PROJECT)

parse-demo:
	uv run klave parse $(DEMO_PROJECT)

process-demo:
	uv run klave process $(DEMO_PROJECT)

eval-demo:
	uv run python -m klave_engine.evals.regression_suite

# Gold set of real drawings (evals/gold/*.json; drawings stay local, matched by hash).
eval-gold:
	uv run python -m klave_engine.evals.gold run

# make gold-capture ROOT=data/uploads/<project> ID=<drawing-id>
gold-capture:
	uv run python -m klave_engine.evals.gold capture $(ROOT) --id $(ID) --fresh

api:
	KLAVE_DATA_DIR=data uv run uvicorn apps.api.main:app --reload --port 8000

web-install:
	npm --prefix apps/web install

web:
	npm --prefix apps/web run dev

clean:
	rm -rf data/demo/*/processed data/demo/*/reports data/demo/*/converted reports/*.json reports/*.md
