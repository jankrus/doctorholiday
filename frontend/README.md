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
| Dev server (http://localhost:5173) | `npm run dev`                                                    |
| Production build to `dist/`        | `npm run build` (type check + Vite)                              |
| Lint and format check              | `npm run lint`                                                   |
| Format                             | `npm run format`                                                 |
| Unit tests                         | `npm test`                                                       |
| Regenerate API types               | `npm run gen:api` (after every change to `backend/openapi.yaml`) |

The dev server proxies `/api` to the backend at `http://localhost:8080`; set `API_PROXY_TARGET` to use another
address. The frontend never calls another origin, so no CORS is needed.

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
