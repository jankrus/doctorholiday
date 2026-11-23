.PHONY: test-gate evidence evidence-sync help up down check-tools cluster cni ingress namespace secrets db-config images deploy wait status logs verify test lint package db-up db-down db-reset test-db sast-sql check-pinning lint-actions
.DEFAULT_GOAL := help

# bash with strict flags, so a failing step stops the target with a clear error (#42).
SHELL := bash
.SHELLFLAGS := -euo pipefail -c

# The cluster targets (up, down, cluster, cni, ingress, secrets, deploy, wait, ...).
include infrastructure/cluster.mk

help: ## List available targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

test: ## Run backend and frontend tests
	$(MAKE) -C backend test
	cd frontend && npm test

lint: ## Run linters
	$(MAKE) -C backend lint
	cd frontend && npm run lint

# Pinned by digest (AGENTS.md rule 7). Only the project rules in .semgrep/, so no network access
# to the Semgrep registry is needed; the pipeline runs the full rule packs (#33).
SEMGREP_IMAGE := semgrep/semgrep:1.140.0@sha256:4372a1de903521f9f10f877b6caf15d150d17e1ca592582682c8d02b77cbd4f6

sast-sql: ## Check the backend for SQL built from strings with Semgrep (#12)
	docker run --rm --network none -v "$(CURDIR):/src:ro" -w /src $(SEMGREP_IMAGE) \
		semgrep scan --metrics off --disable-version-check --error --config .semgrep/ backend/src

# Pipeline checks (#31). Tool images pinned by digest (AGENTS.md rule 7). zizmor runs offline here;
# the pipeline can run its online audits (impostor commits, known-vulnerable actions) with a token.
ACTIONLINT_IMAGE := rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
ZIZMOR_IMAGE := ghcr.io/zizmorcore/zizmor:1.32.0@sha256:3014cc8f68f663935f69b3c3e0e41f5ce102b268d97db13db0f62208747f860d

check-pinning: ## Fail if an action is not pinned by commit SHA or an image not by digest (SR-06, #31)
	scripts/check-pinning.sh

lint-actions: check-pinning ## Lint the workflows with actionlint and zizmor (#31)
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT_IMAGE) -color=false
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ZIZMOR_IMAGE) --offline --no-progress --persona auditor .github/workflows/

test-gate: ## Test the quality gate (each failure mode on fixture reports) (#36)
	python3 scripts/test_quality_gate.py

# Manual fallback of the pipeline's evidence job (#44): rebuilds the evidence of one finished run
# from its artifacts into evidence/ (the working tree), e.g. `make evidence RUN_ID=123456789`.
# The signing and gate artifacts only exist once #35 and #36 are in.
evidence: ## Download the reports of a pipeline run into evidence/ (RUN_ID=<id>, needs gh) (#44)
	@test -n "$(RUN_ID)" || { echo "usage: make evidence RUN_ID=<workflow run id>"; exit 1; }
	@mkdir -p .cache/evidence-$(RUN_ID)/run-logs
	gh run download $(RUN_ID) --dir .cache/evidence-$(RUN_ID)
	@repo=$$(gh repo view --json nameWithOwner --jq .nameWithOwner); \
	scripts/fetch-run-logs.sh "$$repo" $(RUN_ID) .cache/evidence-$(RUN_ID)/run-logs; \
	number=$$(gh run view $(RUN_ID) --json number,headSha --jq '(.number|tostring) + " " + .headSha[0:7]'); \
	scripts/collect-evidence.sh .cache/evidence-$(RUN_ID) evidence "$$(printf '%05d' $${number% *})-$${number#* }"

evidence-sync: ## Copy the evidence branch into evidence/ of this checkout, for the submission PR (#44)
	git fetch origin evidence
	git checkout origin/evidence -- evidence
	@echo "Copied evidence/ from origin/evidence; review it, commit it on a branch and open a pull request."

package: ## Build the team-<nr>.zip submission (#51)
	@echo "TODO: package"

DB_SECRETS := .secrets/db_superuser_password .secrets/db_owner_password .secrets/db_app_password

# Random passwords, created once; the directory is private, the files must be readable by the
# container's postgres user.
$(DB_SECRETS):
	@mkdir -p -m 700 .secrets
	@openssl rand -hex 32 | tr -d '\r' > $@ && chmod 644 $@
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
