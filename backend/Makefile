.PHONY: help install test lint format run lock
.DEFAULT_GOAL := help

# --locked fails if uv.lock does not match pyproject.toml instead of silently updating it.
UV_RUN := uv run --locked

help: ## List available targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## Create .venv with the exact versions from uv.lock
	uv sync --locked

test: ## Run the test suite
	$(UV_RUN) pytest

lint: ## Check lint and formatting (no changes)
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

format: ## Fix lint findings where safe and format the code
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

run: ## Start the API with the variables from .env
	$(UV_RUN) --env-file .env python -m doctorholiday

lock: ## Re-resolve uv.lock after editing pyproject.toml
	uv lock
