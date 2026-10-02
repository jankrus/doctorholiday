.PHONY: help up down test lint package
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
