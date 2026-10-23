# backend

Python 3.12 + FastAPI REST API (ADR-001). Implemented in #11-#22.

`openapi.yaml` is the API contract (OpenAPI 3.1, #4) that backend and frontend implement against. Requirements and business rules behind it: [docs/architecture/requirements.md](../docs/architecture/requirements.md). Lint it with `npx @redocly/cli@2.60.0 lint openapi.yaml`.

## Database

PostgreSQL 16 schema as defined in [docs/architecture/database.md](../docs/architecture/database.md) (#12).

### Local database

```sh
make db-up      # start PostgreSQL on 127.0.0.1:5432 and apply the migrations
make db-down    # stop it, keep the data
make db-reset   # delete the data and rebuild from the migrations
```

`make db-up` creates random passwords in `.secrets/` (git-ignored) on first use. The backend connects as `doctorholiday_app` with the password from `.secrets/db_app_password`; set `DB_PORT` to use another host port.

The container (`compose.yaml`) runs `postgres:16-alpine`, pinned by digest, as UID 70 with a read-only root filesystem, no capabilities and `no-new-privileges`. The port is published on `127.0.0.1` only, and every connection, including the local socket, needs a SCRAM-SHA-256 password.

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
| `credentials`, `sessions`, `recovery_codes`, `password_reset_codes`, `working_hours` | `SELECT, INSERT, UPDATE, DELETE` | Rows are deleted by logout, account deletion, MFA reset or a new schedule. |
| `absences` | `SELECT, INSERT, DELETE` | Absences are created and deleted, never changed (A14, A31). |
| `practice_settings`, `admin_bootstrap` | `SELECT, UPDATE` | Single rows created by the migration; the app cannot add or remove them. |
| `audit_events` | `SELECT, INSERT` | Append-only, the application cannot rewrite the audit log (BR-19). |
| `schema_migrations` | none | Owned by the migration role. |
