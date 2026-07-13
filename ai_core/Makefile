.PHONY: dev worker install lint test

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

dev:
	PYTHONPATH=.:.. uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

worker:
	PYTHONPATH=.:.. celery -A app.worker:celery_app worker --loglevel=INFO -Q ai,render

lint:
	ruff check app tests

test:
	PYTHONPATH=.:.. pytest -q
