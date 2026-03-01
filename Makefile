UV ?= ./scripts/uv
RUFF_TARGETS := app tests scripts

.PHONY: bootstrap install-hooks lint fmt test test-unit test-integration ci

bootstrap:
	./scripts/bootstrap

install-hooks:
	./scripts/install_hooks

lint:
	./scripts/lint

fmt:
	./scripts/fmt

test:
	./scripts/test

test-unit:
	./scripts/test

test-integration:
	$(UV) run pytest -m integration

ci:
	./scripts/ci
