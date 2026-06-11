.PHONY: install test lint typecheck demo-data ingest-demo convert-demo parse-demo process-demo eval-demo api dashboard clean

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

api:
	uv run uvicorn apps.api.main:app --reload --port 8000

dashboard:
	uv run streamlit run apps/dashboard/app.py

clean:
	rm -rf data/demo/*/processed data/demo/*/reports data/demo/*/converted reports/*.json reports/*.md
