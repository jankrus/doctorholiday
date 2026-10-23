.PHONY: help up down test lint package db-up db-down db-reset
.DEFAULT_GOAL := help

help: ## List available targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up: ## Create kind cluster and deploy the app (#42)
	@echo "TODO: up"

down: ## Delete the kind cluster (#42)
	@echo "TODO: down"

test: ## Run backend and frontend tests (#11, #23)
	@echo "TODO: test"

lint: ## Run linters (#11, #23)
	@echo "TODO: lint"

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
