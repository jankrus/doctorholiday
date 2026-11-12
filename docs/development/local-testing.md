# Local development and manual testing

How to run Doctor Holiday from source on your own machine (database, backend, frontend in the browser) and check
features by hand. The Kubernetes deployment (`make up`) is a separate path (#42); the automated checks are listed in
[AGENTS.md](../../AGENTS.md#run-tests-and-linters-locally).

**Keep it current:** a PR that adds or changes a user-visible feature adds or updates its section in
[Manual test scenarios](#5-manual-test-scenarios) (AGENTS.md rule 9). A PR that changes setup steps or ports
updates this guide too.

Contents: [1. Requirements](#1-requirements) · [2. One-time setup](#2-one-time-setup) ·
[3. Start the stack](#3-start-the-stack) · [4. Look into the database](#4-look-into-the-database) ·
[5. Manual test scenarios](#5-manual-test-scenarios) · [6. Troubleshooting](#6-troubleshooting)

## 1. Requirements

| Tool | Version | Check |
| :--- | :--- | :--- |
| Git | any recent | `git --version` |
| Docker with Compose v2 (Docker Desktop, OrbStack, or Docker Engine) | running | `docker compose version` |
| GNU make | 3.81+ | `make --version` |
| [uv](https://docs.astral.sh/uv/) | 0.12.23 to < 0.13 (`backend/pyproject.toml`) | `uv --version` |
| Node.js | 22.13+ (`engines` in `frontend/package.json`; `frontend/.nvmrc`) | `node --version` |
| openssl, curl | any | `openssl version`, `curl --version` |

uv installs Python 3.12 by itself. Supported systems: **macOS** and **Linux**. On **Windows**, use WSL 2: clone the
repository inside the WSL file system (not under `/mnt/c`), enable Docker Desktop's WSL integration and run every
command in the WSL shell; the Makefile and scripts need a POSIX shell. Git Bash and PowerShell do not work: among
other things, the generated secrets in `.secrets/` get CRLF line endings and the database passwords stop matching.

## 2. One-time setup

From the repository root:

```sh
make db-up                          # starts PostgreSQL on 127.0.0.1:5432; creates random DB passwords in .secrets/
(cd backend && make install)        # Python virtualenv from backend/uv.lock
(cd frontend && npm ci)             # Node modules from frontend/package-lock.json
cp backend/.env.example backend/.env
```

Fill in `backend/.env` (it is git-ignored; never commit it). This replaces the three `CHANGE_ME` values with the app
role's database password and freshly generated secrets; it works with both GNU and BSD (macOS) `sed`:

```sh
cd backend
APP_PW=$(cat ../.secrets/db_app_password)
SESSION_SECRET=$(openssl rand -base64 32)
MFA_KEY=$(uv run --locked python -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')
sed -i.bak \
  -e "s#^DATABASE_URL=.*#DATABASE_URL=postgresql+psycopg://doctorholiday_app:${APP_PW}@localhost:5432/doctorholiday#" \
  -e "s#^SESSION_SECRET=.*#SESSION_SECRET=${SESSION_SECRET}#" \
  -e "s#^MFA_ENCRYPTION_KEY=.*#MFA_ENCRYPTION_KEY=${MFA_KEY}#" \
  .env && rm .env.bak
cd ..
```

Optional, for [seed data](../../backend/README.md#seed-data) (one account per role): uncomment `SEED_DEV_DATA=true`
in `backend/.env` and set `SEED_PASSWORD` to a passphrase of 12+ characters that you can type at the login.

`.secrets/` survives `make db-reset`, so `backend/.env` stays valid after a reset. Only if you delete `.secrets/`
yourself do you have to run the snippet again.

## 3. Start the stack

Three terminals, all from the repository root:

| # | Command | Check |
| :- | :--- | :--- |
| 1 | `make db-up` (if not running yet) | `docker compose ps` shows `db` as `healthy` |
| 2 | `make -C backend run` | `curl -s http://localhost:8080/readyz` prints `{"status":"ready"}` |
| 3 | `cd frontend && API_PROXY_TARGET=http://localhost:8080 npm run dev` | `curl -i http://localhost:5173/api/v1/auth/me` answers `401` with a JSON body |

Then open **http://localhost:5173** (not `127.0.0.1:5173`, see [Troubleshooting](#6-troubleshooting)). The Vite dev
server forwards `/api` to the backend, so the browser sees one origin, as behind the ingress.

Without `API_PROXY_TARGET`, `npm run dev` answers `/api` with a **mock** that accepts any password and fakes
endpoints the backend does not have yet ([frontend/README.md](../../frontend/README.md#dev-server)). It is useful for
UI work, but it proves nothing about the backend. Use the real backend for anything security-related (status codes,
rate limits, roles).

### Pick a database state

| State | How | Use for |
| :--- | :--- | :--- |
| **Fresh**: no accounts, admin bootstrap still open | `make db-reset` | the first-admin bootstrap (#15), registration |
| **Seeded**: one account per role, working hours, two appointments | `make db-reset && make -C backend seed` | everything that needs `STAFF` or `DOCTOR` accounts |

`make db-reset` deletes all local data, including accounts, sessions and rate limit counters. The backend can keep
running; its pool reconnects.

### Accounts

- **Registration always creates a `PATIENT`** (BR-02).
- **The first successful login on a fresh database becomes `ADMIN`** (#15). On a seeded database the seeded
  `dev-admin@example.com` is the admin and nobody else is promoted.
- **`STAFF` and `DOCTOR`** accounts exist only through the seed data until invitations (FR-02) are built.
- After login the frontend sends each role to its start page: `PATIENT` → `/appointments`, `STAFF`/`DOCTOR` →
  `/staff`, `ADMIN` → `/admin`. "Abmelden" in the header logs out.
- Use a private window (or a second browser) to be logged in as two accounts at once.
- E-mail addresses need a real-looking domain such as `@example.com`; `.test` and `.localhost` are rejected.

### Testing the API with curl

The login response already contains the role. To call endpoints that need a session, copy the token from the
`Set-Cookie` header:

```sh
API=http://localhost:8080/api/v1/auth
PW='correct horse battery staple'
reg()   { curl -s -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"$PW\"$2}" "$API/register"; }
login() { curl -s -i -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"${2:-$PW}\"}" "$API/login"; echo; }

reg a@example.com                     # 202
login a@example.com                   # 200, Set-Cookie: __Host-dh_session=<token>; body with "role"
curl -s -H 'Cookie: __Host-dh_session=<token>' "$API/me"
curl -s -X POST -o /dev/null -w '%{http_code}\n' -H 'Cookie: __Host-dh_session=<token>' "$API/logout"   # 204
```

## 4. Look into the database

```sh
docker compose exec -e PGPASSWORD="$(cat .secrets/db_superuser_password)" db \
  psql -h 127.0.0.1 -U postgres -d doctorholiday
```

Useful queries:

```sql
SELECT email, role, is_active FROM users ORDER BY created_at;
SELECT * FROM admin_bootstrap;
SELECT timestamp, action, outcome, actor_id, target, ip, details FROM audit_events ORDER BY timestamp DESC LIMIT 20;
SELECT user_id, state, created_at, last_seen_at FROM sessions;
```

This connects as the superuser; the backend itself only has the grants of `doctorholiday_app`
([backend/README.md](../../backend/README.md#database-roles)). Change data by hand only to set up a test (e.g.
deactivating an account), and reset afterwards.

## 5. Manual test scenarios

Each scenario lists the starting state, the steps and what you should see. Automated tests cover the same rules;
manual testing checks that the pieces work together in a real browser.

### Authentication (#14)

Start: any database state, real backend.

| # | Steps | Expected |
| :- | :--- | :--- |
| A1 | Register at `/register`, log in at `/login` | After registering: "Vielen Dank für Ihre Registrierung. Sie können sich jetzt anmelden." Login lands on the start page of the role; the header shows the e-mail and "Abmelden". |
| A2 | DevTools → Application/Storage → Cookies → `localhost:5173` | One cookie `__Host-dh_session`, `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, no expiry (session cookie). |
| A3 | Click "Abmelden" | Back on `/login` with "Sie wurden abgemeldet."; the cookie is gone; going back to the start page asks for a login again. |
| A4 | Log in with a wrong password, then with an unknown e-mail | Both show "E-Mail-Adresse oder Passwort ist falsch." The API answers `401 INVALID_CREDENTIALS` for both, identical apart from the request ID. |
| A5 | Register an e-mail that already exists | Same success message as A1; nothing changes (no account enumeration). The old password still works. |
| A6 | Fail the login of one e-mail 5 times, then try the correct password | The 6th attempt shows "Zu viele Versuche. …" (`429`, header `Retry-After`) and the correct password is refused too, for 15 minutes. |
| A7 | Register with an 11-character password | The form shows "Bitte verwenden Sie mindestens 12 Zeichen." and sends nothing. The API rejects it too: `reg x@example.com` with `PW='short pass1'` gives `422`. 12 characters work. |
| A8 | Register with a common password, e.g. `passwordpassword` | API: `422 PASSWORD_TOO_COMMON`. **Known gap:** the frontend has no text for this code yet and shows the generic "Etwas ist schiefgelaufen." ([#90](https://github.com/jankrus/doctorholiday/issues/90)) |
| A9 | `docker compose exec … psql` (section 4): `SELECT action, outcome, details FROM audit_events ORDER BY timestamp DESC LIMIT 10;` | `USER_REGISTERED`, `LOGIN` (`SUCCESS`, or `FAILURE` with `reason`), `LOGOUT`; never an e-mail address or password. |

### First-admin bootstrap (#15)

Start: **fresh database** (`make db-reset`, no seed) for B1 to B4, a reset before each of B2 to B4.

| # | Steps | Expected |
| :- | :--- | :--- |
| B1 | Register A and B. Log in as A, then as B (private window), then as A again | A lands on `/admin` ("Verwaltung"), B on `/appointments` ("Meine Termine"), A again on `/admin`. The login response and `/api/v1/auth/me` show `"role": "ADMIN"` for A right away. |
| B1 (DB) | Queries from section 4 | `admin_bootstrap`: `bootstrapped = t`, `admin_id` = A's id. `users`: A `ADMIN`, B `PATIENT`. Exactly one `ADMIN_BOOTSTRAPPED` event: actor and target A, your IP, `details` empty. |
| B2 | Register X, log in with a wrong password; then register Y and log in correctly | X's failed login changes nothing (`admin_bootstrap.bootstrapped = f`); Y becomes `ADMIN`. |
| B3 | Register X, fail 5 times, then the correct password (`429`); then register Y and log in | No admin after X; Y becomes `ADMIN`. |
| B4 | Register X, deactivate it in psql (`UPDATE users SET is_active = false WHERE email = '…';`), log in with the correct password; then register Y and log in | X gets `401` and is not promoted; Y becomes `ADMIN`. |
| B5 | `reg c@example.com ',"role":"ADMIN"'` (curl helpers above) | `422 VALIDATION_ERROR`, no account created; the same for `"role":"PATIENT"`. |
| B6 | Seeded database: register and log in a new account | Stays `PATIENT`; `admin_bootstrap.admin_id` stays the seeded admin. |

Two parallel first logins becoming admin at once cannot be reproduced reliably by hand (all local requests share one
IP and its rate limit counter, which already serialises them); `make test-db` covers it with
`test_concurrent_first_logins_promote_exactly_one`.

Not built yet, so not testable: MFA enrolment of the new admin (#21) and the `/setup` page after the bootstrap
(`setupRequired`, needs `PUT /api/v1/settings`).

## 6. Troubleshooting

Start with `curl -s http://localhost:8080/readyz`: `{"status":"ready"}` means backend and database are fine.

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| Every page or form shows "Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut."; the backend terminal shows a long traceback; `/readyz` says `not_ready` | The backend cannot reach the database: DB not running, or `DATABASE_URL` in `backend/.env` has the wrong port or password. Port `55432` belongs to the throwaway database of `make test-db` and is never right here. | `docker compose ps`; `make db-up`; set `DATABASE_URL` again with the snippet in [section 2](#2-one-time-setup); restart the backend. |
| API calls through the dev server return `404` with an empty body; `curl localhost:8080/readyz` returns `404` | Another program listens on port 8080 (often bound to `127.0.0.1`, which wins over the backend's all-interfaces socket) | Find it: `lsof -nP -iTCP:8080 -sTCP:LISTEN` (macOS/Linux). Stop it, or run the backend elsewhere: `PORT=8081` in `backend/.env` and `API_PROXY_TARGET=http://localhost:8081`. |
| Login accepts any password; e-mails like `admin@…` behave specially | The dev server runs the mock | Restart it with `API_PROXY_TARGET=http://localhost:8080`. |
| `http://127.0.0.1:5173` refuses the connection | The dev server may listen on IPv6 `::1` only | Open `http://localhost:5173`. |
| The first login did not become `ADMIN` | The bootstrap is already used: an earlier login on this database, or seed data | `make db-reset` (without seeding) and log in first. |
| `429` / "Zu viele Versuche" during testing | All local requests come from one IP: 20 failed logins per 15 minutes (any account) or 10 registrations per 60 minutes lock it | Wait, or `make db-reset` (deletes the counters). For long manual sessions you may raise `REGISTRATION_MAX_PER_IP` / `LOGIN_MAX_FAILURES_PER_IP` in your own `backend/.env`; never in shared config. |
| `make db-up`: port 5432 is already allocated | A local PostgreSQL or another container uses it | `DB_PORT=5433 make db-up` and use `:5433` in `DATABASE_URL`. |
| The backend exits at start with `invalid configuration` | Missing or invalid variable in `backend/.env`; the log names the variables, never their values | Compare with `backend/.env.example`; every `CHANGE_ME` must be replaced. |
| `make -C backend seed` says `refused` | `SEED_DEV_DATA` is not `true`, `DATABASE_URL` is not local, or `SEED_PASSWORD` is too common | See [Seed data](../../backend/README.md#seed-data). |
| `uv` complains about its version | `backend/pyproject.toml` requires uv 0.12.23 to < 0.13 | `uv self update` or install a matching version. |
| An app page has no data | Booking and admin screens are placeholders until #17, #25 and #26 | Expected for now. |

**Network exposure:** the backend listens on all interfaces (it is built for the container, where the pod network
is the boundary), so on your laptop other devices in the same network can reach port 8080. Use a trusted network or
your firewall while it runs, and never put real data into the local database. A configurable bind address with a
loopback default is planned in [#91](https://github.com/jankrus/doctorholiday/issues/91).
