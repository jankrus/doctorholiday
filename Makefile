.PHONY: help up down test lint package db-up db-down db-reset test-db
.DEFAULT_GOAL := help

help: ## List available targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up: ## Create kind cluster and deploy the app (#42)
	@echo "TODO: up"

down: ## Delete the kind cluster (#42)
	@echo "TODO: down"

test: ## Run backend and frontend tests
	$(MAKE) -C backend test
	cd frontend && npm test

lint: ## Run linters
	$(MAKE) -C backend lint
	cd frontend && npm run lint

package: ## Build the team-<nr>.zip submission (#51)
	@echo "TODO: package"

DB_SECRETS := .secrets/db_superuser_password .secrets/db_owner_password .secrets/db_app_password

# Random passwords, created once; the directory is private, the files must be readable by the
# container's postgres user.
$(DB_SECRETS):
	@mkdir -p -m 700 .secrets
	@openssl rand -hex 32 > $@ && chmod 644 $@
	@echo "Created $@"

db-up: $(DB_SECRETS) ## Start local PostgreSQL and apply the migrations (#12)
	docker compose up --detach --wait db
	docker compose run --rm migrate

db-down: ## Stop local PostgreSQL, keep its data
	docker compose down

db-reset: ## Delete the local database and recreate it from the migrations
	docker compose down --volumes
	$(MAKE) db-up

# Throwaway database for the backend's database tests: same compose file, init script and
# migrate.sh, but its own compose project, port and volume, so the dev database is never touched.
TEST_DB := docker compose --project-name doctorholiday-test
test-db: export DB_PORT := $(or $(TEST_DB_PORT),55432)

test-db: $(DB_SECRETS) ## Run the backend tests against a fresh, migrated PostgreSQL (deleted afterwards)
	@$(TEST_DB) down --volumes --remove-orphans 2>/dev/null
	$(TEST_DB) up --detach --wait db
	$(TEST_DB) run --rm migrate
	@status=0; \
	TEST_DATABASE_URL="postgresql+psycopg://doctorholiday_app:$$(cat .secrets/db_app_password)@127.0.0.1:$$DB_PORT/doctorholiday" \
		$(MAKE) -C backend test || status=$$?; \
	$(TEST_DB) down --volumes; \
	exit $$status
