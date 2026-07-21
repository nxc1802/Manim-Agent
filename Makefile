.PHONY: dev-be dev-ai worker-ai dev-fe install-be install-ai install-fe lock test-be test-ai test-fe lint-be lint-ai lint-fe build-fe schema-check audit check image compose-up

dev-be:
	$(MAKE) -C backend dev

dev-ai:
	$(MAKE) -C ai_core dev

worker-ai:
	$(MAKE) -C ai_core worker

dev-fe:
	cd frontend && npm run dev

install-be:
	$(MAKE) -C backend install

install-ai:
	$(MAKE) -C ai_core install

install-fe:
	cd frontend && npm ci

lock:
	$(MAKE) -C backend lock
	$(MAKE) -C ai_core lock

test-be:
	$(MAKE) -C backend test

test-ai:
	$(MAKE) -C ai_core test

test-fe:
	cd frontend && npm test

lint-be:
	$(MAKE) -C backend lint

lint-ai:
	$(MAKE) -C ai_core lint

lint-fe:
	cd frontend && npm run lint

build-fe:
	cd frontend && npm run build

schema-check:
	bash backend/supabase/validate_migrations.sh

audit:
	$(MAKE) -C backend audit
	$(MAKE) -C ai_core audit
	cd frontend && npm audit --audit-level=high

check: lint-be lint-ai lint-fe test-be test-ai test-fe build-fe schema-check

image:
	docker build --build-arg VITE_AUTH_MODE=off -t manim-agent:local .

compose-up:
	docker compose up --build
