# backend

Python 3.12 + FastAPI REST API (ADR-001). Implemented in #11-#22.

`openapi.yaml` is the API contract (OpenAPI 3.1, #4) that backend and frontend implement against. Requirements and business rules behind it: [docs/architecture/requirements.md](../docs/architecture/requirements.md). Lint it with `npx @redocly/cli@2.60.0 lint openapi.yaml`.

## Tooling: uv

Dependencies, the virtualenv and the Python version are managed with **[uv](https://docs.astral.sh/uv/)**, see [ADR-002](../docs/architecture/adr/ADR-002-python-package-manager.md). Do not use `pip install` or hand-written `requirements.txt` files in this directory.

| File | Purpose |
| :--- | :--- |
| `pyproject.toml` | Direct dependencies, dev dependency group, ruff and pytest config, required uv version |
| `uv.lock` | Exact versions + hashes of all packages. Committed, never edited by hand |
| `.python-version` | Python 3.12 (uv downloads it if your system has another version) |
| `.env.example` | All environment variables with placeholders; copy to `.env` |

## Setup

1. Install uv in the version range from `[tool.uv] required-version` in `pyproject.toml` (currently 0.12.x):
   ```sh
   brew install uv                                     # macOS
   curl -LsSf https://astral.sh/uv/install.sh | sh     # Linux/macOS, see docs.astral.sh/uv
   uv --version
   ```
2. Create the virtualenv `.venv` with exactly the locked versions (also installs Python 3.12 if missing):
   ```sh
   cd backend
   make install            # = uv sync --locked
   ```
3. Configure the environment:
   ```sh
   cp .env.example .env    # .env is git-ignored; never commit it
   ```
   Replace every `CHANGE_ME`; the comments in `.env.example` show how to generate each secret. The app refuses to start with missing or invalid values.
4. Start a PostgreSQL 16 for `/readyz` (until docker-compose lands in #29), with the same password as in `DATABASE_URL`:
   ```sh
   docker run -d --rm --name dh-postgres -p 127.0.0.1:5432:5432 \
     -e POSTGRES_USER=doctorholiday -e POSTGRES_DB=doctorholiday -e POSTGRES_PASSWORD=<your password> \
     postgres:16-alpine
   ```
5. Run the API on `http://localhost:8080`:
   ```sh
   make run                # = uv run --locked --env-file .env python -m doctorholiday
   curl -i localhost:8080/healthz
   ```

## Daily commands

Run from `backend/`; `make help` lists all targets. From the repo root, `make test` / `make lint` run the same checks.

| Task | Make | Plain uv |
| :--- | :--- | :--- |
| Install / update `.venv` from the lockfile | `make install` | `uv sync --locked` |
| Tests | `make test` | `uv run --locked pytest` |
| Lint + format check | `make lint` | `uv run --locked ruff check . && uv run --locked ruff format --check .` |
| Auto-fix + format | `make format` | `uv run ruff check --fix . && uv run ruff format .` |
| Run the API | `make run` | `uv run --locked --env-file .env python -m doctorholiday` |

## Changing dependencies

```sh
uv add <package>          # runtime dependency
uv add --dev <package>    # test/lint tooling only, never shipped in the image
uv remove <package>
uv lock --upgrade-package <package>   # update one package within the allowed range
```

Each command updates `pyproject.toml` **and** `uv.lock`; commit both together. If `uv sync --locked` or `make test` fails with "The lockfile needs to be updated", someone changed `pyproject.toml` without re-locking: run `uv lock` and commit the result. Keep runtime dependencies minimal, because each one widens the SCA surface (Trivy, #33).

## Configuration

Read only from environment variables and validated at startup (`src/doctorholiday/config.py`). On an invalid configuration the process logs the variable names and reasons (never the values) and exits with code 1.

| Variable | Required | Format |
| :--- | :--- | :--- |
| `DATABASE_URL` | yes | `postgresql+psycopg://user:password@host:port/db` |
| `SESSION_SECRET` | yes | at least 32 characters |
| `MFA_ENCRYPTION_KEY` | yes | 32 random bytes, base64url with padding (44 characters) |
| `ALLOWED_ORIGINS` | yes | comma-separated `http(s)://host[:port]` origins, no wildcard |
| `PORT` | no (8080) | 1024-65535 |
| `LOG_LEVEL` | no (`INFO`) | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

## Code layout

```
src/doctorholiday/
  __main__.py     entry point: config, logging, uvicorn (SIGTERM = graceful shutdown)
  main.py         create_app(): FastAPI app, middleware, routers
  config.py       Settings from environment variables
  logs.py         JSON logging to stdout, redaction of sensitive fields
  middleware.py   request ID (X-Request-Id), access log
  db.py           SQLAlchemy engine, readiness check
  api/health.py   GET /healthz, GET /readyz
tests/            pytest
```

Conventions for new code:

- **Synchronous data access** ([ADR-003](../docs/architecture/adr/ADR-003-synchronous-data-access.md)): endpoints that use the database or other blocking code are `def`, not `async def`.
- **Logging:** use `logging.getLogger(__name__)` and pass data via `extra={...}`. Every line is JSON on stdout with the `requestId` of the current request. Never log passwords, session IDs, tokens, MFA secrets or request bodies. Fields with such names are redacted, but that is a safety net, not a licence.
- **Request ID:** every response carries a fresh UUID in `X-Request-Id`, also available as `request.state.request_id` (used by the error responses in #13). Client-supplied IDs are ignored.
- **Files:** the container runs with a read-only root filesystem. Write nothing to disk; if unavoidable, only below `/tmp`.
- **No API docs at runtime:** `/docs`, `/redoc` and `/openapi.json` are disabled; the contract is `openapi.yaml`.
