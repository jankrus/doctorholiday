# backend

Python 3.12 + FastAPI REST API (ADR-001). Implemented in #11-#22.

`openapi.yaml` is the API contract (OpenAPI 3.1, #4) that backend and frontend implement against. Requirements and business rules behind it: [docs/architecture/requirements.md](../docs/architecture/requirements.md). Lint it with `npx @redocly/cli@2.60.0 lint openapi.yaml`.
