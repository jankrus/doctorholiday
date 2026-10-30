# Database Schema (Physical ER Model)

This document and the diagram [`database-erm.drawio`](database-erm.drawio) define the PostgreSQL 16 schema that the migrations of [#12](https://github.com/jankrus/doctorholiday/issues/12) create. The logical model (entities, fields, meaning) stays in [requirements.md](requirements.md#domain-model); this is its physical form: column types, nullability, defaults, keys, constraints and indexes.

- **Diagram:** open `database-erm.drawio` in draw.io (desktop, web or the VS Code extension). Each table shows its columns; the dashed box below a table lists its constraints and indexes.
- **Builds on:** [requirements.md](requirements.md) (domain model, BR-01–BR-25), [roles-and-permissions.md](roles-and-permissions.md), [ADR-001](adr/ADR-001-tech-stack.md) (PostgreSQL 16, SQLAlchemy 2).
- **Open PR included:** the model already contains the schema change of an open PR, marked yellow in the diagram: `users.mfa_offer_declined_at` (#67, optional MFA for patients). If that PR is dropped, its column is dropped here too.

## Conventions

| Topic | Decision |
| --- | --- |
| Names | Tables plural, columns snake_case, as listed in #12. `starts_at`/`ends_at` instead of `start`/`end` (SQL keyword). |
| Primary keys | Random `uuid` with `DEFAULT gen_random_uuid()` (built into PostgreSQL 13+), so IDs cannot be enumerated. The two single-row tables use `smallint id = 1`. |
| Enums | `text` + `CHECK (col IN (…))` instead of PostgreSQL `ENUM` types. Adding a value is a plain constraint change in a migration, and the values match the OpenAPI enums one to one. |
| Time | Every timestamp is `timestamptz` (stored in UTC). Only `working_hours` uses `time`, because it is local time in `Europe/Berlin` (BR-08). |
| E-mail | Domain `email_address` over `citext` (case-insensitive uniqueness), see requirements.md. |
| Secrets | Only hashes or ciphertext: `password_hash` (Argon2id), `token_hash` (SHA-256, 32 bytes), `code_hash`, `mfa_secret_enc`. Raw tokens and codes never reach the database. `rate_limits.key_hash` is the SHA-256 of an IP, e-mail address or user ID, so failed logins with unknown e-mails leave no address in clear. |
| Deletion | Users, appointments and audit events are never deleted; account deletion erases personal data instead (BR-13). Rows that only exist for a user's login (`credentials`, `sessions`, `recovery_codes`, `password_reset_codes`) use `ON DELETE CASCADE`; every other FK keeps the default `NO ACTION`, so history can never lose its references. |
| Extensions | `citext` (e-mail), `btree_gist` (exclusion constraints mixing `=` on `uuid`/`smallint` with `&&` on ranges). |

## Additions to the logical model

The physical model needed four things the first version of the domain model did not have. The three columns are now part of the domain model in requirements.md; the exclusion constraints are physical only.

| Addition | Why |
| --- | --- |
| `credentials.totp_last_step` (`bigint`, `NULL`) | RFC 6238 §5.2: a verifier must not accept the same TOTP code twice. Stores the time step of the last accepted code; codes with a step `<=` this value are rejected. Without it, a code observed by an attacker stays valid for its 30 s window (#21). |
| `audit_events.details` (`jsonb`, `NULL`) | BR-22 requires the audit event of a rescheduling to record the old and the new time, and `target` holds only one ID. `details` takes a small object with allow-listed keys only (e.g. `oldStartsAt`, `newStartsAt`, `oldDoctorId`, `newDoctorId`, `oldRole`, `newRole`); the audit module never copies request bodies or personal data into it (BR-19). |
| `admin_access_grants.expiry_logged_at` (`timestamptz`, `NULL`) | BR-17 requires an `APPOINTMENT_ACCESS_EXPIRED` audit event when a grant expires. The column marks grants whose event was written, so the event is written exactly once even if several pods or job runs see the same expired grant. |
| Exclusion constraints on `working_hours` and `admin_access_grants` | BR-08 (entries of one weekday do not overlap) and BR-17 (only one active grant per admin) are checked by the backend, but two concurrent requests can both pass the check. As with appointments (BR-09), the database is the final guard. `working_hours` needs the range type `timerange` over `time`, which the first migration creates. |

## Rate limiting

`rate_limits` holds the counters of BR-03 and is not part of the logical model: its rows are technical, short-lived and reference no user, because unknown e-mails are counted too. Migration V005 created it as `login_throttles` for login only; V006 renamed it and added the scopes of the other endpoints.

| Column | Type | Meaning |
| --- | --- | --- |
| `scope` | `text`, `CHECK IN (…)` | Endpoint and key type: `LOGIN_IP`, `LOGIN_ACCOUNT`, `REGISTRATION_IP`, `MFA_VERIFICATION_USER`, `INVITATION_ACCEPTANCE_IP`, `PASSWORD_RESET_IP`, `REAUTHENTICATION_USER`. IPs are counted per address (IPv6 per /64), e-mails in lower case |
| `key_hash` | `bytea`, 32 bytes | SHA-256 of the key; PK `(scope, key_hash)` |
| `window_started_at` | `timestamptz`, default `now()` | Start of the counting window; index `(scope, window_started_at)` for the cleanup of expired rows |
| `attempts` | `smallint`, default 0, `>= 0` | Counted attempts in the window (failures for login, every request for registration) |
| `locked_until` | `timestamptz`, `NULL` | Set when `attempts` reaches the limit; requests with this key answer `429` until then |

The application role has `SELECT, INSERT, UPDATE, DELETE`: a successful login deletes its e-mail row, and every request deletes the rows of its scope whose window and lockout are over.

## Constraints the database cannot express

These rules stay in the backend and need tests there (#12, #14–#18):

- **Role of a referenced user:** `doctor_id` must reference a `DOCTOR`, `patient_id` a `PATIENT`, `admin_id` an `ADMIN`. A plain FK cannot check this, and the role can change later (BR-15), which must not invalidate history.
- **Counting rules:** at most 5 working-hours entries per weekday (BR-08), 5 open appointments per patient or guest phone (BR-09, BR-24), 100 open absences per doctor (BR-12). Each check runs in the same transaction as the insert.
- **Time-relative rules:** "in the future", "at most 365 days ahead", cancellation deadline (BR-11, BR-12, BR-23) depend on `now()` and do not belong in `CHECK` constraints.
- **Last active admin** (BR-15): checked under `SELECT … FOR UPDATE` on the admin rows.
- **Absence vs. booked appointment** (BR-12): checked in the transaction that creates the absence.

## Rows created by the migrations

Both single-row tables are filled by the migration, not by dev seed data, so a fresh cluster works without seeding:

- `practice_settings`: `(1, 'Doctor Holiday', 24, 15, now(), NULL)`; `updated_by_id IS NULL` means the practice setup is still pending (BR-18).
- `admin_bootstrap`: `(1, false, NULL, NULL)`; the first login locks this row (BR-04).

## Database roles and grants

Least privilege; the roles, the exact privileges per table and how migrations run are documented in [`backend/README.md`](../../backend/README.md#database), the statements are in `infrastructure/postgres/init/00-roles.sh` and `backend/migrations/V004__app_grants.sql` (later migrations grant on the tables they add, e.g. V005 on `rate_limits`):

- **Owner/migration role** (`doctorholiday_owner`) owns the database and schema and runs the migrations. It is not a superuser: `citext` and `btree_gist` are trusted extensions (PostgreSQL 13+), so a role with `CREATE` on the database can install them.
- **Application role** (`doctorholiday_app`, used by the running backend) has no `CREATE` on the schema and no DDL rights. It gets `DELETE` only on tables whose rows the domain deletes, no `INSERT`/`DELETE` on the two single-row tables, and on `audit_events` only `SELECT, INSERT`, so the application cannot rewrite the audit log.
