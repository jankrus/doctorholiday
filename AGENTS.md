# AGENTS.md

Read this first. Then read the exam brief and every issue listed under *Dependencies* of your ticket.

## Purpose
**Doctor Holiday**: appointment booking system for a doctor's practice (frontend + backend), built for the exam
"Security by Design" (STG-TINF24F). Security and a reproducible supply chain matter more than features.
Deviations from the brief are allowed only if justified in `docs/report/deviations.md`.

- Exam brief: [docs/sbd_pruefungsleistung_3er.pdf](docs/sbd_pruefungsleistung_3er.pdf)
- Tech stack decision: [ADR-001](docs/architecture/adr/ADR-001-tech-stack.md)
- Project board / tickets: https://github.com/users/jankrus/projects/1/

## Directory map (layout fixed by exam brief §7a)
| Path | Content |
| :--- | :--- |
| `frontend/` | React 18 + TypeScript + Vite SPA, served by nginx-unprivileged |
| `backend/` | Python 3.12 + FastAPI REST API (`backend/openapi.yaml` = API contract) |
| `infrastructure/k8s/` | Kubernetes manifests (Kustomize) |
| `infrastructure/kind/` | kind cluster config |
| `infrastructure/postgres/` | DB role init script and migration runner; migrations live in `backend/migrations/` |
| `compose.yaml` | Local PostgreSQL for development (`make db-up`) |
| `.github/workflows/` | CI/CD pipeline |
| `scripts/` | Helper scripts (quality gate, packaging, cluster setup) |
| `evidence/<image>/{run,sast,sbom,sca,secrets,signing}/` | Pipeline reports per image (`frontend`, `backend`) |
| `docs/architecture/`, `threat-model/`, `report/`, `presentation/` | Documentation |
| `VERSION.txt` | SemVer, single line, used as image tag |
| `Makefile` | Project blueprint: `make up` must yield a healthy cluster and print `Ready` |

## Stack (details in ADR-001)
- Frontend: React 18, Vite 5, ESLint 8, Vitest
- Backend: FastAPI 0.110+, SQLAlchemy 2, Pydantic 2, `passlib` + `argon2-cffi` (Argon2id), `pyotp` (TOTP), `ruff`, `pytest`
- DB: PostgreSQL 16
- Auth: server-side sessions in `HttpOnly; Secure; SameSite=Strict` cookies (no JWT in browser storage)
- Pipeline: GitHub Actions, GHCR, Syft (SBOM), Semgrep (SAST), Trivy (SCA/image), Gitleaks, cosign (key-based)
- Deploy: local `kind` + `ingress-nginx`, driven by the Makefile
- Base images: distroless/chainguard (backend), `nginxinc/nginx-unprivileged:alpine`, `postgres:16-alpine`; **pinned by sha256 digest**

## Naming
- Kubernetes namespace: `doctorholiday`
- Images: `ghcr.io/jankrus/doctorholiday-frontend`, `ghcr.io/jankrus/doctorholiday-backend`
- Containers listen on unprivileged ports (8080), numeric non-root UID (e.g. 10001)

## Rules (non-negotiable)
1. **No hardcoded secrets.** All config via environment variables, validated at startup. Only dummy values in `.env.example`. Never commit `.env`, `*.key`, `*.pem`.
2. **Every endpoint is input-validated (Pydantic) and authorized** (RBAC + object-level checks; foreign objects return 404).
3. **Errors never leak internals**: generic messages to clients, details only in structured logs. Never log passwords, session IDs, MFA secrets or full bodies.
4. **Parametrized queries only** (SQLAlchemy); no string-built SQL.
5. **Read-only root filesystem**: write only to `/tmp`.
6. **Least privilege in K8s**: own namespace, minimal ServiceAccount, `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, NetworkPolicy default deny.
7. **Supply chain**: pin dependencies via lockfile, pin GitHub Actions by commit SHA and images by digest. The quality gate blocks on secrets, CVSS >= 7.0 (HIGH/CRITICAL) and missing/invalid signatures.
8. Keep changes scoped to your ticket; open a follow-up issue for anything else.
9. Update affected docs in the same PR.

## Git / PR conventions
- Never push to `main` directly. Use feature branches, e.g. `feat/<ticket>-<slug>`, `docs/...`, `fix/...`.
- [Conventional Commits](https://www.conventionalcommits.org/): `feat(backend): add login endpoint`.
- PR description contains `Closes #<n>`; PR merges only when the ticket's acceptance criteria are checked off.
- Pushes to `main` trigger the pipeline.

## Run tests and linters locally
| Task | Command |
| :--- | :--- |
| All tests / lint | `make test` / `make lint` (stubs until #11, #23, #42) |
| Backend tests | `cd backend && pytest` |
| Backend lint | `cd backend && ruff check . && ruff format --check .` |
| API contract lint | `cd backend && npx @redocly/cli@2.60.0 lint openapi.yaml` |
| Frontend tests | `cd frontend && npm ci && npm test` |
| Frontend lint | `cd frontend && npm run lint` |
| Cluster up / down | `make up` / `make down` |
| Local DB up (+ migrations) / down / reset | `make db-up` / `make db-down` / `make db-reset` |

Commands become valid as the respective skeleton tickets land; update this table when they do.
