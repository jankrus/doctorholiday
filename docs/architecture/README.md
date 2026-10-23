# docs/architecture

Architecture decisions (`adr/`), requirements, RBAC matrix, architecture diagram (#1-#6).

- [roles-and-permissions.md](roles-and-permissions.md): roles, permission matrix, admin bootstrap and role assignment rules (#3)
- [requirements.md](requirements.md): functional requirements, business rules, domain model with ER diagram, API conventions (#4); the API contract itself is [`backend/openapi.yaml`](../../backend/openapi.yaml)
- [database.md](database.md) and [database-erm.drawio](database-erm.drawio): physical ER model of the PostgreSQL schema (types, keys, constraints, indexes, grants) for the migrations (#12)
