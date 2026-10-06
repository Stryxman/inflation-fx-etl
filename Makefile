-include .env
export

PY ?= .venv/bin/python
.PHONY: venv up down etl transform check test lint psql reset
venv:
	python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
up:
	docker compose up -d --wait
down:
	docker compose down
etl:
	$(PY) -m etl run
transform:
	$(PY) -m etl transform
check:
	$(PY) -m etl check
test:
	$(PY) -m pytest -q
lint:
	.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy etl
psql:
	docker compose exec db psql -U $${POSTGRES_USER:-etl} -d $${POSTGRES_DB:-etl}
reset:
	docker compose down -v
