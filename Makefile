.PHONY: dev-be dev-fe install-be install-fe test-be lint-be

dev-be:
	$(MAKE) -C backend dev

dev-fe:
	cd frontend && npm run dev

install-be:
	$(MAKE) -C backend install

install-fe:
	cd frontend && npm install

test-be:
	$(MAKE) -C backend test

lint-be:
	$(MAKE) -C backend lint
