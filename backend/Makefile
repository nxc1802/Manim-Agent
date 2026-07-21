.PHONY: dev install lock test lint audit

PYTHON ?= python3

install:
	$(PYTHON) -m pip install --require-hashes -r requirements-dev.lock

lock:
	uv pip compile pyproject.toml --extra dev --python-version 3.12 --python-platform x86_64-manylinux_2_36 --exclude-newer 2026-07-21T23:59:59Z --generate-hashes -o requirements-dev.lock
	uv pip compile pyproject.toml --python-version 3.12 --python-platform x86_64-manylinux_2_36 --exclude-newer 2026-07-21T23:59:59Z --generate-hashes -o requirements.lock

dev:
	PYTHONPATH=.:.. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	PYTHONPATH=.:.. pytest -q

lint:
	ruff check app tests

audit:
	pip-audit --strict --no-deps --disable-pip --progress-spinner=off -r requirements.lock
	pip-audit --strict --no-deps --disable-pip --progress-spinner=off -r requirements-dev.lock
