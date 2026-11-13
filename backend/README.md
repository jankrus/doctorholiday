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

To run database, backend and frontend together and test by hand, follow [docs/development/local-testing.md](../docs/development/local-testing.md); it includes a snippet that fills in `.env`. The steps for the backend alone:

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
4. Start the local PostgreSQL with the schema (from the repo root, see [Database](#database)) and put the app role's password from `.secrets/db_app_password` into `DATABASE_URL`:
   ```sh
   make db-up
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
| `SESSION_IDLE_TIMEOUT_MINUTES` | no (30) | 1-1440; a session ends after this long without a request |
| `SESSION_ABSOLUTE_TIMEOUT_MINUTES` | no (480) | 1-10080, at least the idle timeout; a session ends this long after the login |
| `LOGIN_MAX_FAILURES_PER_ACCOUNT` | no (5) | 1-100; failed logins per e-mail address within the window before it is locked |
| `LOGIN_MAX_FAILURES_PER_IP` | no (20) | 1-1000; failed logins per client IP within the window before it is locked |
| `LOGIN_FAILURE_WINDOW_MINUTES` | no (15) | 1-1440; how long failed logins are counted |
| `LOGIN_LOCKOUT_MINUTES` | no (15) | 1-1440; how long a locked e-mail or IP gets `429` |
| `REGISTRATION_MAX_PER_IP` | no (10) | 1-1000; registrations per client IP within the window before it is locked |
| `REGISTRATION_WINDOW_MINUTES` | no (60) | 1-1440; how long registrations are counted, and how long a locked IP gets `429` |

`SESSION_SECRET` is validated but not used yet: session tokens are random and only their hash is stored, so they need no signing key (#59).

## Code layout

```
src/doctorholiday/
  __main__.py     entry point: config, logging, uvicorn (SIGTERM = graceful shutdown)
  main.py         create_app(): FastAPI app, middleware, routers
  config.py       Settings from environment variables
  errors.py       error responses in the contract's Error shape, exception handlers
  validation.py   RequestModel, shared field types, rejection of unknown query parameters
  logs.py         JSON logging to stdout, redaction of sensitive fields
  middleware.py   request ID (X-Request-Id), access log, generic 500, body size and JSON checks
  db.py           SQLAlchemy engine, per-request transaction (DbSession), readiness check
  models.py       ORM models mirroring the migrated schema, enums
  repositories/   data access layer: the only code that builds queries
  auth/           passwords (Argon2id), session tokens and cookie, CurrentSession/ActiveUser,
                  rate limiting (rate_limiting.py)
  api/health.py   GET /healthz, GET /readyz
  api/auth.py     POST /api/v1/auth/register, /login, /logout, GET /api/v1/auth/me
tests/            pytest; tests/db/ needs a database (`make test-db`)
```

Conventions for new code:

- **Synchronous data access** ([ADR-003](../docs/architecture/adr/ADR-003-synchronous-data-access.md)): endpoints that use the database or other blocking code are `def`, not `async def`.
- **Data access:** see [Data access layer](#data-access-layer).
- **Logging:** use `logging.getLogger(__name__)` and pass data via `extra={...}`. Every line is JSON on stdout with the `requestId` of the current request. Never log passwords, session IDs, tokens, MFA secrets or request bodies. Fields with such names are redacted, but that is a safety net, not a licence.
- **Request ID:** every response carries a fresh UUID in `X-Request-Id`, also available as `request.state.request_id` (used in the `requestId` of every error body). Client-supplied IDs are ignored.
- **Files:** the container runs with a read-only root filesystem. Write nothing to disk; if unavoidable, only below `/tmp`.
- **Errors** (#13): raise `ApiError(status, ErrorCode.X, "generic message")`; the handler in `errors.py` answers with `{"error": {"code", "message", "requestId"}}`. Raising rolls back the request transaction, so an endpoint that must keep its writes (e.g. the audit event of a failed login) returns `error_response(...)` instead. Every other error gets the same shape, a generic message and `X-Request-Id` = `requestId`:

  | Cause | Answer | Where |
  | :--- | :--- | :--- |
  | Invalid JSON, schema violation, unknown body field or query parameter | `422 VALIDATION_ERROR` | `errors.py`, `validation.py` |
  | Body over 16 KiB (`MAX_BODY_BYTES`) | `413 PAYLOAD_TOO_LARGE` | `RequestBodyMiddleware` |
  | Non-empty body that is not `application/json` | `415 UNSUPPORTED_MEDIA_TYPE` | `RequestBodyMiddleware` |
  | Unknown path / unsupported method | `404 NOT_FOUND` / `405 METHOD_NOT_ALLOWED` with `Allow` | `errors.py` |
  | `DataConflictError` not caught by the endpoint | `409 TIME_ALREADY_BOOKED` or `409 CONFLICT` | `errors.py` |
  | Any other exception | `500 INTERNAL_ERROR`; traceback in the log (`unhandled exception`) | `RequestContextMiddleware` |

  Responses never contain the submitted values, parser messages, the framework's `detail`, stack traces or file paths; the validation log has field locations and error types only. The `500` is answered in `RequestContextMiddleware`, not by an exception handler, because Starlette runs those outside every middleware, so the response would lack `X-Request-Id`. New error codes go into `ErrorCode` in `openapi.yaml` first; `tests/test_errors.py` fails otherwise.
- **Validation** (#13, SR-03): request bodies subclass `RequestModel` (`extra="forbid"`) and use the field types in `validation.py` (`Email`, `Password`, `NewPassword`, `DisplayName`) or give every string and every list a `max_length`. Query parameters a route does not declare are rejected. `tests/test_validation.py` fails for any route whose body, path, query, header or cookie parameters are unbounded or whose body is not a `RequestModel`, and for any endpoint that reads the raw body (`request.json()` etc.). E-mail addresses are trimmed and lowercased, display names trimmed; passwords are never changed.
- **No API docs at runtime:** `/docs`, `/redoc` and `/openapi.json` are disabled; the contract is `openapi.yaml`.

## Authentication

MVP subset of #14: register, login, logout and `/me` with a server-side session (ADR-001, BR-01 to BR-05), and login rate limiting with temporary lockout. The first-admin bootstrap (#15) is in place. Still missing: MFA, CSRF protection, invitations, rate limiting of the other endpoints BR-03 names (registration etc.). Temporary shortcuts are marked `MVP-TEMP` in the code and in `openapi.yaml`:

- Every session is `ACTIVE`; there is no MFA step yet.
- `GET /auth/me` never returns `setupRequired`, because `PUT /api/v1/settings` does not exist yet.

How it works:

- **Passwords** are hashed with Argon2id (`argon2-cffi`, RFC 9106 low-memory parameters) and are 12-128 characters, not trimmed (BR-01). They are `SecretStr` in the request models, so they never appear in a repr or traceback.
- **Common passwords** are rejected at registration with `422 PASSWORD_TOO_COMMON` (BR-01, NIST SP 800-63B): `auth/common_passwords.txt.gz` holds 46,825 casefolded entries of 12-128 characters from the NCSC top 100,000 and the xato.net top 1,000,000 (SecLists, MIT licence, pinned commit and SHA-256). Rebuild it with `python3 -I scripts/build-common-passwords.py`; the output is byte-for-byte reproducible. It is gzipped so secret scanners do not report random-looking entries as leaked keys. Passwords containing the service name (`doctorholiday`, ignoring spaces, hyphens, dots and underscores) or the account's e-mail address are rejected too. The check runs after the rate limit, so rejected attempts still count, and before the e-mail lookup, so it reveals no accounts. Invitation acceptance, password change and reset use `is_common_password` too when they are built.
- **Sessions:** login creates a token with `secrets.token_urlsafe(32)` (256 bits); `sessions.token_hash` holds only its SHA-256. The cookie is `__Host-dh_session=<token>; HttpOnly; Secure; SameSite=Strict; Path=/`, without `Max-Age`, so it ends with the browser session. Every request checks the idle and the absolute timeout against the database clock and refreshes `last_seen_at` in the same `UPDATE`. Logout deletes the row and clears the cookie. Several sessions per user (devices) are allowed.
- **Session fixation:** the token is always new. A cookie sent along with a login is never adopted, and the session it names (if it timed out) is deleted. Register and login with a valid session answer `403 FORBIDDEN`.
- **No account enumeration:** register always answers `202` without body; for a taken e-mail nothing is created, but the password is still hashed so the response takes as long (BR-02). Login answers the same `401 INVALID_CREDENTIALS` for an unknown e-mail, a wrong password and a deactivated account, and checks unknown e-mails against a dummy hash (BR-03).
- **Rate limiting and lockout** (BR-03; `auth/rate_limiting.py`, table `rate_limits`): a `Limit` allows a number of counted attempts per key (client IP, e-mail or user) within a window; the attempt that reaches it locks the key for the lockout time, and every request with that key answers `429 RATE_LIMITED` with `Retry-After` before doing the protected work. After a lockout ends, attempts still inside the window lock again at once. Counters live in the database (across restarts and pods), keyed by scope and the SHA-256 of the key, compared with the database clock and row-locked for the rest of the request, so parallel requests cannot overshoot a limit. Expired counters of a scope are deleted by later requests of that scope. An endpoint creates a `RateLimiter` with its limits before the protected work, answers `429` if `retry_after()` says so, and calls `count()` for each attempt that counts. Implemented so far:
  - **Login:** failed logins are counted per e-mail address and per client IP (IPv6: per /64). 5 failures per e-mail or 20 per IP within 15 minutes lock that key for 15 minutes; meanwhile every login with it answers `429 RATE_LIMITED` with `Retry-After`, without checking the password, so not even the right one gets through. The IP limit is higher because a practice or household shares one IP behind NAT. Every failure cause counts (unknown e-mail, wrong password, deactivated account), and unknown e-mails get a counter too, so a lockout reveals no accounts. A successful login resets the e-mail counter, never the IP counter, so a known account cannot reset the IP limit between guesses. Trade-off: anyone can lock an account for 15 minutes with 5 wrong passwords; the values are configurable (see [Configuration](#configuration)).
  - **Registration:** every request counts per client IP, whatever the e-mail, so the limit reveals no accounts either: 10 within 60 minutes, then the IP is locked for 60 minutes. A locked request is answered before the password is hashed, so a flood costs no Argon2id time.
  - **Still to come** with their endpoints (scopes already in the schema, limits in BR-03): MFA verification (#76, with #21), invitation acceptance (#77, with #55), password reset (#78, with #61), re-authentication for password change and account deletion (#79, with #66 and #18).
- **Registration** always creates a `PATIENT` (BR-02); a `role` field is rejected with `422 VALIDATION_ERROR` like any unknown field. Until invitations (FR-02) exist, `STAFF` and `DOCTOR` test accounts come only from the [seed data](#seed-data).
- **First-admin bootstrap** (exam brief §4, BR-04; `repositories/admin_bootstrap.py`): the first login that passes every check (rate limit, password, active account) while `admin_bootstrap` says no admin exists promotes that account to `ADMIN`, in the login transaction and before the session is created, so the login response and `/me` already show the new role. The row is locked with `SELECT … FOR UPDATE`, so of parallel first logins exactly one is promoted; once it is set, logins only read it. A failed, inactive or rate-limited login never bootstraps. A database reset re-arms it. Still missing: the new admin's MFA enrolment before anything else (#21).
- **Who is calling:** `CurrentSession` (any session state, for `/me` and `/logout`) and `ActiveUser` (`ACTIVE` sessions only, else `403 MFA_REQUIRED`) in `auth/dependencies.py` resolve cookie → hash → session → active user and answer `401 UNAUTHENTICATED` otherwise. New endpoints that need a login take `user: ActiveUser`. A deactivated user's sessions stop working immediately.
- **Audit:** `USER_REGISTERED`, `LOGIN` (`SUCCESS`/`FAILURE` with `details.reason`), `LOGOUT`, `ADMIN_BOOTSTRAPPED` (the promoted account as actor and target), with the user as target and the client IP; never an e-mail address. A rate-limited request is audited as `LOGIN` or `USER_REGISTERED` `FAILURE` with `reason: RATE_LIMITED`; the start of a lockout is logged as a warning. The IP is the direct peer; behind ingress-nginx that is the proxy until forwarded headers are handled (#75), and until then all clients share one IP counter.
- Responses with session data send `Cache-Control: no-store`.
- E-mail addresses are validated with `email-validator`, which rejects special-use domains such as `.test` or `.localhost`; use e.g. `@example.com` for test accounts.

## Database

PostgreSQL 16 schema as defined in [docs/architecture/database.md](../docs/architecture/database.md) (#12).

### Data access layer

- **The migrations own the schema.** `models.py` mirrors the tables for SQLAlchemy and is never used to create or alter them. A new column needs a migration *and* the model change; `tests/db/test_schema.py` fails if the two drift apart (columns, nullability, defaults, foreign keys).
- **One transaction per request.** An endpoint that needs the database takes `session: DbSession`. The transaction is committed when the endpoint returns and rolled back on any exception; repositories never commit. The commit runs before the response is sent (`Depends(..., scope="function")`), so a failed commit is never answered with a success status.
- **Queries only in `repositories/`**, built with SQLAlchemy (bound parameters, AGENTS.md rule 4). No `text()` with values spliced in, no f-strings with SQL. `make sast-sql` (repo root) checks `src/` for SQL built from strings with the project's Semgrep rule (`.semgrep/raw-sql.yml`); ruff's `S608` checks the same while linting.
- **The database is the final guard for conflicts.** Overlapping bookings (`appointments_no_overlap`) and duplicate e-mails (`users_email_key`) are rejected by constraints, also for concurrent requests. Repositories run such inserts in a SAVEPOINT and raise a `DataConflictError` subclass (`TimeAlreadyBookedError`, `EmailAlreadyRegisteredError`), which the API maps to 409. A check before the insert is for user feedback only. `book_appointment` first locks the doctor's `users` row (`FOR NO KEY UPDATE`, until the transaction ends), so bookings of one doctor run one after the other: without it, concurrent conflicting inserts wait for each other's uncommitted rows and PostgreSQL aborts one with a deadlock error instead of the constraint violation. Repositories for the other exclusion constraints (`working_hours`, `admin_access_grants`) need the same per-owner lock.
- **Database errors carry personal data.** The message and `DETAIL` of an `IntegrityError` contain the offending values (e.g. an e-mail address or the whole row). Never return them, and never log `str(exc)`; log the constraint name (`db.violated_constraint`) instead (rule 3, #13).
- **No ORM relationships.** Every read is an explicit query and nothing loads lazily; in particular no attribute leads from a `User` to its `Credential`, which only the auth module reads.

### Database tests

```sh
make test-db    # from the repo root
```

Starts a throwaway PostgreSQL (compose project `doctorholiday-test`, port 55432, override with `TEST_DB_PORT`), applies the migrations with the same `migrate.sh`, runs the whole backend suite with `TEST_DATABASE_URL` pointing at it as `doctorholiday_app`, and deletes the database afterwards. Running as the app role means the tests also check its grants. `make test` without a database skips `tests/db/`.

Each test runs in a transaction that is rolled back. The concurrency tests in `test_concurrent_booking.py` commit for real from several connections, which is fine because the database is thrown away.

### Local database

```sh
make db-up      # start PostgreSQL on 127.0.0.1:5432 and apply the migrations
make db-down    # stop it, keep the data
make db-reset   # delete the data and rebuild from the migrations
```

`make db-up` creates random passwords in `.secrets/` (git-ignored) on first use. The backend connects as `doctorholiday_app` with the password from `.secrets/db_app_password`; set `DB_PORT` to use another host port.

The container (`compose.yaml`) runs `postgres:16-alpine`, pinned by digest, as UID 70 with a read-only root filesystem, no capabilities and `no-new-privileges`. The port is published on `127.0.0.1` only, and every connection, including the local socket, needs a SCRAM-SHA-256 password.

### Seed data

```sh
make -C backend seed   # after make db-up; needs SEED_DEV_DATA=true and SEED_PASSWORD in backend/.env
```

For local development only (#12). Creates `dev-admin@example.com`, `dev-staff@example.com`, `dev-doctor-1@example.com`, `dev-doctor-2@example.com`, `dev-patient-1@example.com` and `dev-patient-2@example.com`, all with the password from `SEED_PASSWORD`. The doctors get working hours Monday to Friday 08:00-12:00 and 14:00-17:00, and each patient one booked appointment next week. The seeded admin is recorded in `admin_bootstrap`, so the first-login bootstrap (#15) promotes no one else; the practice setup stays pending. Until invitations (FR-02) exist, this is the only way to get `STAFF` and `DOCTOR` accounts: registration always creates a `PATIENT`.

Guards (`doctorholiday/seed.py`): it is a one-off command, never part of the app's startup; it refuses to run unless `SEED_DEV_DATA=true` and `DATABASE_URL` points at `localhost`, `127.0.0.1` or `::1`, so it cannot run against the cluster database; `SEED_PASSWORD` must pass the registration policy (BR-01) and is never printed. Seeding twice changes nothing. To start over: `make db-reset` (repo root), then seed again.

### Migrations

Plain SQL files in [`migrations/`](migrations), named `V<nnn>__<name>.sql` and applied in order by [`infrastructure/postgres/migrate.sh`](../infrastructure/postgres/migrate.sh). It runs as a separate one-off command, not at backend startup: the `migrate` service in `compose.yaml` (run by `make db-up` and `docker compose up`), later a Kubernetes Job with the same script and image (#39). The backend therefore never needs DDL rights.

- Each file runs in one transaction together with its row in `schema_migrations` (version, SHA-256, time); a failing file leaves nothing behind.
- Re-runs skip applied files, so the command is idempotent.
- A file that was changed after it was applied stops the run. Never edit an applied migration; add a new one.
- A migration that creates a table also grants the application role its privileges on it.

### Database roles

| Role | Created by | Rights |
| --- | --- | --- |
| `postgres` | image (first start) | Superuser. Only used by `infrastructure/postgres/init/00-roles.sh` on the first start; nothing connects with it afterwards. |
| `doctorholiday_owner` | `00-roles.sh` | Owns the database and schema `public`, runs the migrations. Not a superuser, cannot create roles or databases; `citext` and `btree_gist` are trusted extensions it may install. |
| `doctorholiday_app` | `00-roles.sh` | Used by the running backend. `CONNECT` on the database, `USAGE` on `public`, no `CREATE`, no DDL, no `TRUNCATE`, and only the table privileges below ([`V004__app_grants.sql`](migrations/V004__app_grants.sql)). |

`PUBLIC` has no rights on the database or schema `public`. Table privileges of `doctorholiday_app`:

| Table | Privileges | Why not more |
| --- | --- | --- |
| `users`, `appointments`, `invitations`, `admin_access_grants` | `SELECT, INSERT, UPDATE` | Never deleted (BR-11, BR-13); expired invitations and grants stay as history. |
| `credentials`, `sessions`, `recovery_codes`, `password_reset_codes`, `working_hours`, `rate_limits` | `SELECT, INSERT, UPDATE, DELETE` | Rows are deleted by logout, account deletion, MFA reset, a new schedule, a successful login or the expiry of a rate limit counter. |
| `absences` | `SELECT, INSERT, DELETE` | Absences are created and deleted, never changed (A14, A31). |
| `practice_settings`, `admin_bootstrap` | `SELECT, UPDATE` | Single rows created by the migration; the app cannot add or remove them. |
| `audit_events` | `SELECT, INSERT` | Append-only, the application cannot rewrite the audit log (BR-19). |
| `schema_migrations` | none | Owned by the migration role. |
