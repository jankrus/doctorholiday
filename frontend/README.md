# frontend

React 18 + TypeScript SPA built with Vite into static assets, served by nginx-unprivileged (#28).
Libraries and versions: [ADR-001](../docs/architecture/adr/ADR-001-tech-stack.md) and
[ADR-004](../docs/architecture/adr/ADR-004-frontend-libraries.md) (Radix Themes, React Router 7, `openapi-fetch`).

## Setup

Requires Node.js 22.13+ (`.nvmrc`). Install exactly what the lockfile pins:

```sh
npm ci
```

## Commands

| Task                               | Command                                                          |
| :--------------------------------- | :--------------------------------------------------------------- |
| Dev server (http://localhost:5173) | `npm run dev` (mock API, see [Dev server](#dev-server))          |
| Production build to `dist/`        | `npm run build` (type check + Vite)                              |
| Lint and format check              | `npm run lint`                                                   |
| Format                             | `npm run format`                                                 |
| Unit tests                         | `npm test`                                                       |
| Regenerate API types               | `npm run gen:api` (after every change to `backend/openapi.yaml`) |

## Dev server

### Without a backend (default)

`npm run dev` starts a mock API inside the dev server ([`dev-mock-api.ts`](dev-mock-api.ts)), so all pages can be
viewed and the auth flows clicked through. It answers the session, login, registration, logout, MFA and settings
endpoints; other API calls get `503`. The e-mail address used to log in picks the flow (any password works, except
`falsch`):

| E-mail                           | Flow                                                    |
| :------------------------------- | :------------------------------------------------------ |
| `patient@…` (or anything else)   | logged in; MFA offer until accepted or declined (BR-26) |
| `mfa@…`                          | MFA code required (every code works except `000000`)    |
| `staff@…`, `doctor@…`, `admin@…` | MFA enrolment first; the first admin then sees `/setup` |
| `limit@…`                        | `429` too many attempts                                 |

To jump to a state directly, open one of these URLs; it redirects to the matching start page:

| URL                                                             | Session                    |
| :-------------------------------------------------------------- | :------------------------- |
| `/__mock/session?as=none`                                       | none (default)             |
| `/__mock/session?as=PATIENT` (or `STAFF`, `DOCTOR`, `ADMIN`)    | logged in with that role   |
| `/__mock/session?as=PATIENT_MFA_OFFER`                          | patient, MFA offer pending |
| `/__mock/session?as=ADMIN_SETUP`                                | admin, setup pending       |
| `/__mock/session?as=MFA_PENDING` (or `MFA_ENROLLMENT_REQUIRED`) | waiting for MFA            |

The mock only exists in the dev server; it is never part of `npm run build`.

### With a backend

Set `API_PROXY_TARGET` to forward `/api` to a running backend instead of the mock:

```sh
API_PROXY_TARGET=http://localhost:8080 npm run dev
```

Either way the frontend only calls its own origin, so no CORS is needed.

## Structure

```text
src/
  api/client.ts      typed API client (same origin, session cookie, CSRF hook for #19)
  api/errors.ts      maps API errors to fixed, generic user-facing texts
  api/schema.d.ts    generated from backend/openapi.yaml, do not edit
  auth/session.ts    current session via GET /api/v1/auth/me
  auth/guards.ts     route guards (UX only; the backend authorises every request)
  auth/validation.ts client-side checks mirroring the API contract (server stays authoritative)
  auth/logout.ts     logout action (POST /auth/logout, back to /login)
  components/        shared UI: form fields, notices, QR code, copy and logout buttons, logo, icons
  pages/auth/        split-screen auth layout; login, register, MFA and setup pages
  pages/             app layout, error and placeholder pages
  routes.tsx         route table
```

## Design

Colours, typography, layout and form patterns are described in the
[UI design guide](../docs/architecture/ui-design.md). `/login` and `/register` are the reference implementation.

## Routes

| Path                  | Who                                                                     | Built in |
| :-------------------- | :---------------------------------------------------------------------- | :------- |
| `/login`, `/register` | no session                                                              | #24      |
| `/mfa`                | MFA verification or enrolment pending, or a patient's MFA offer (BR-26) | #24      |
| `/setup`              | `ADMIN` whose practice setup is pending (BR-18)                         | #24      |
| `/logout`             | form target (`POST`) of every logout button                             | #24      |
| `/appointments`       | `PATIENT`                                                               | #25      |
| `/staff`              | `STAFF`, `DOCTOR`                                                       | #26      |
| `/admin`              | `ADMIN`                                                                 | #26      |

Without a session every protected route redirects to `/login`; other roles are sent to their own start page.
The first login creates the admin (BR-04, #15); `GET /api/v1/auth/me` then returns `setupRequired: true` and
every route forwards the admin to `/setup` until the practice settings are saved for the first time.
