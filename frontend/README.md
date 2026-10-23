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
viewed. It answers `GET /api/v1/auth/me` and nothing else (other API calls get `503`). Pick the session the
frontend sees by opening one of these URLs; it redirects to the matching start page:

| URL                                                             | Session                  |
| :-------------------------------------------------------------- | :----------------------- |
| `/__mock/session?as=none`                                       | none (default)           |
| `/__mock/session?as=PATIENT` (or `STAFF`, `DOCTOR`, `ADMIN`)    | logged in with that role |
| `/__mock/session?as=MFA_PENDING` (or `MFA_ENROLLMENT_REQUIRED`) | waiting for MFA          |

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
  api/client.ts     typed API client (same origin, session cookie, CSRF hook for #19)
  api/errors.ts     maps API errors to fixed, generic user-facing texts
  api/schema.d.ts   generated from backend/openapi.yaml, do not edit
  auth/session.ts   current session via GET /api/v1/auth/me
  auth/guards.ts    route guards (UX only; the backend authorises every request)
  pages/            layout, error and placeholder pages
  routes.tsx        route table
```

## Routes

| Path                  | Who                                               | Built in |
| :-------------------- | :------------------------------------------------ | :------- |
| `/login`, `/register` | no session                                        | #24      |
| `/mfa`                | session waiting for MFA verification or enrolment | #24      |
| `/appointments`       | `PATIENT`                                         | #25      |
| `/staff`              | `STAFF`, `DOCTOR`                                 | #26      |
| `/admin`              | `ADMIN`                                           | #26      |

Without a session every protected route redirects to `/login`; other roles are sent to their own start page.
There is no `/setup` route: the first admin is created by the first login (BR-04, #15).
