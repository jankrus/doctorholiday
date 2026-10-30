# docs/architecture

Architecture decisions (`adr/`), requirements, RBAC matrix, architecture diagram (#1-#6).

- [roles-and-permissions.md](roles-and-permissions.md): roles, permission matrix, admin bootstrap and role assignment rules (#3)
- [requirements.md](requirements.md): functional requirements, business rules, domain model with ER diagram, API conventions (#4); the API contract itself is [`backend/openapi.yaml`](../../backend/openapi.yaml)
- [adr/ADR-001-tech-stack.md](adr/ADR-001-tech-stack.md): application stack, base images, platform tooling (#1)
- [adr/ADR-002-python-package-manager.md](adr/ADR-002-python-package-manager.md): uv as Python package and environment manager, lockfile rules (#11)
- [adr/ADR-003-synchronous-data-access.md](adr/ADR-003-synchronous-data-access.md): synchronous SQLAlchemy/psycopg data access in the backend (#11)
- [adr/ADR-004-frontend-libraries.md](adr/ADR-004-frontend-libraries.md): frontend libraries (#23)
