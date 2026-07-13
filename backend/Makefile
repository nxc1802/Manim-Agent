.PHONY: dev install test lint

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

dev:
	PYTHONPATH=.:.. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	PYTHONPATH=.:.. pytest -q

lint:
	ruff check app tests
