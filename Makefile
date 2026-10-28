.PHONY: help up down test lint package
.DEFAULT_GOAL := help

help: ## List available targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up: ## Create kind cluster and deploy the app (#42)
	@echo "TODO: up"

down: ## Delete the kind cluster (#42)
	@echo "TODO: down"

test: ## Run backend and frontend tests (frontend: #23)
	$(MAKE) -C backend test
	@echo "TODO: frontend test (#23)"

lint: ## Run linters (frontend: #23)
	$(MAKE) -C backend lint
	@echo "TODO: frontend lint (#23)"

package: ## Build the team-<nr>.zip submission (#51)
	@echo "TODO: package"
