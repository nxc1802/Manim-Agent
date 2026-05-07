.PHONY: dev install lint typecheck test test-cov test-e2e smoke-hf worker worker-tts docker-build-api docker-build-worker docker-build-tts-worker

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e ".[dev]"

dev:
	mkdir -p storage/logs
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 2>&1 | tee storage/logs/uvicorn.log

lint:
	ruff check backend primitives shared tests worker

worker:
	mkdir -p storage/logs
	celery -A worker.celery_app:celery_app worker --loglevel=INFO -Q render 2>&1 | tee storage/logs/celery_render.log

worker-tts:
	mkdir -p storage/logs
	celery -A worker.celery_app:celery_app worker --loglevel=INFO -Q tts -n tts@%h 2>&1 | tee storage/logs/celery_tts.log

docker-build-api:
	docker build -f docker/api/Dockerfile -t manim-agent-api:dev .

docker-build-worker:
	docker build -f docker/worker/Dockerfile -t manim-agent-worker:dev .

docker-build-tts-worker:
	docker build -f docker/tts-worker/Dockerfile -t manim-agent-tts-worker:dev .

typecheck:
	mypy backend primitives shared worker

test:
	pytest tests/unit -q

smoke-hf:
	bash scripts/ops/smoke_hf_spaces.sh

test-e2e:
	$(PYTHON) -m pytest tests/e2e -m e2e -q --tb=short

test-cov:
	pytest tests/unit -q \
		--cov=backend/core \
		--cov=backend/services \
		--cov=primitives \
		--cov=shared/schemas \
		--cov=worker \
		--cov-report=term-missing \
		--cov-fail-under=72
