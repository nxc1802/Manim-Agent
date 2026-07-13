.PHONY: dev-be dev-ai worker-ai dev-fe install-be install-ai install-fe test-be test-ai lint-be lint-ai compose-up

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
	cd frontend && npm install

test-be:
	$(MAKE) -C backend test

test-ai:
	$(MAKE) -C ai_core test

lint-be:
	$(MAKE) -C backend lint

lint-ai:
	$(MAKE) -C ai_core lint

compose-up:
	docker compose up --build
