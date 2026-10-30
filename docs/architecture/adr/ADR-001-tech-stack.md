# ADR-001: Technology Stack & DevSecOps Platform

## 1. Context
As part of the "Security by Design" exam, a secure appointment booking system for a doctor's office is being developed. The primary focus lies on security, a reproducible supply chain, and deployment to a local Kubernetes cluster. While the choice of programming languages is entirely open, it must be well-justified for each component, specifically regarding security features. Since every subsequent implementation task depends on these decisions, this ADR defines the complete application stack, base images, and platform tooling to ensure consistency across the project.

## 2. Considered Options

### 2.1. Frontend
*   **Option A: React (TypeScript) + Vite**
    *   *Pros:* Massive community, excellent SAST tool support (Semgrep), type safety via TypeScript. Built-in escaping natively protects against most XSS attacks.
    *   *Cons:* Requires a separate build setup and a web server component (Nginx) for deployment.
*   **Option B: Vue.js (TypeScript) + Vite**
    *   *Pros:* Flat learning curve, also features strong security defaults.
    *   *Cons:* SAST rule sets are often more granular and mature for React.

### 2.2. Backend
*   **Option A: Python (FastAPI)**
    *   *Pros:* Rapid development, native and strict input validation via Pydantic (prevents injection attacks early). Excellent cryptographic ecosystem (Argon2, TOTP). Distroless images for Python are well-established.
    *   *Cons:* Not a compiled language (unlike Go), which slightly increases the container size even when using distroless images.
*   **Option B: C# (ASP.NET Core Web API)**
    *   *Pros:* Strong out-of-the-box security mechanisms, type safety, excellent *chiseled* images provided by Microsoft for minimal attack surfaces.
    *   *Cons:* Slightly higher boilerplate overhead compared to FastAPI.

### 2.3. Database
*   **Option A: PostgreSQL**
    *   *Pros:* Industry standard, robust access control, perfectly aligns with Kubernetes Network Policies (Least Privilege). Mature container images (e.g., Alpine-based non-root images) are available.
    *   *Cons:* Requires slightly more resources than file-based databases.
*   **Option B: SQLite**
    *   *Pros:* No network exposure required, minimal complexity.
    *   *Cons:* Hard to securely persist in a Kubernetes environment (with ephemeral pods); less suitable for demonstrating Network Policies.

### 2.4. Session Management & Auth
*   **Option A: Server-Side Sessions with HttpOnly Cookies (Recommended)**
    *   *Pros:* Session identifiers are protected from JavaScript (and thus XSS). SameSite attributes reliably prevent CSRF attacks.
    *   *Cons:* Requires state management (e.g., in the DB) on the backend.
*   **Option B: Stateless JWT (JSON Web Tokens)**
    *   *Pros:* Completely stateless, easy to scale.
    *   *Cons:* Secure storage in the browser is complex. If stored in Local Storage, they are vulnerable to XSS; invalidating them (logout) before expiration is difficult to implement.

### 2.5. Password Hashing
*   **Option A: Argon2id** (Modern standard, memory- and CPU-hard, highly resistant to GPU cracking).
*   **Option B: bcrypt** (Proven and reliable, but older and slightly more vulnerable to brute-force attacks on modern hardware compared to Argon2).

## 3. Decision Outcome

We have decided to use the combination of **React** (Frontend), **Python/FastAPI** (Backend), and **PostgreSQL** (Database). 
For authentication, we will use **Server-Side Sessions with a strict HttpOnly, Secure, SameSite=Strict cookie** to structurally eliminate token theft via XSS. Passwords will be hashed using **Argon2id**. All Docker images will be based on hardened minimal images (`distroless` or `alpine` / `unprivileged`) and will be strictly pinned by digest (SHA-256) in the pipeline to prevent supply chain attacks.

### 3.1. Libraries and Versions

*   **Frontend:**
    *   Framework: React v18
    *   Build Tool: Vite v5
    *   Linter: ESLint v8
    *   Testing: Vitest
*   **Backend:**
    *   Language: Python 3.12
    *   Framework: FastAPI v0.110+
    *   ORM / Query Layer: SQLAlchemy v2 (using parameterized queries to prevent SQL injection); synchronous API, see [ADR-003](ADR-003-synchronous-data-access.md)
    *   Validation: Pydantic v2 (e-mail addresses with `email-validator`)
    *   Auth / Session: Custom implementation based on FastAPI dependencies. Implemented (#14) with an opaque random token whose SHA-256 is stored server-side, so neither `itsdangerous` nor `fastapi-users` is used.
    *   Password Hashing: `argon2-cffi` (Argon2id), used directly. Originally `passlib` on top of it; dropped in #14 because `passlib` is unmaintained (last release 1.7.4 in 2020) and still imports the `crypt` module, which Python 3.12 deprecates and 3.13 removes.
    *   TOTP (MFA): `pyotp` v2.9
    *   Linter / Formatter: `ruff`
    *   Testing: `pytest`
    *   Package / environment manager: `uv` with `uv.lock`, see [ADR-002](ADR-002-python-package-manager.md)
*   **Database:**
    *   Engine: PostgreSQL 16

### 3.2. Container Base Images & Mapping

| Component | Language / Tool | Framework | Base Image (to be pinned by digest) |
| :--- | :--- | :--- | :--- |
| **Frontend** | TypeScript / HTML | React / Nginx | `nginxinc/nginx-unprivileged:alpine` |
| **Backend** | Python 3.12 | FastAPI | `cgr.dev/chainguard/python` (or `gcr.io/distroless/python3`) |
| **Database** | SQL | PostgreSQL | `postgres:16-alpine` |

### 3.3. DevSecOps Platform Tooling (Pre-decided)
All components will pass through the strictly defined CI/CD pipeline:
*   **CI/CD:** GitHub Actions
*   **Container Registry:** GHCR (GitHub Container Registry)
*   **Image Signing:** cosign (key-based signing and verification in the Quality Gate)
*   **SBOM Generation:** Syft
*   **SAST:** Semgrep (scanning React and Python code)
*   **SCA & Image Scan:** Trivy
*   **Secret Scanning:** Gitleaks
*   **Deployment:** Local `kind` cluster with `ingress-nginx` via Makefile automation.

## 4. Consequences (Pros & Cons)

*   **Security (Pros):** Using FastAPI combined with Pydantic automatically validates payloads at the type level, strongly supporting the secure coding requirements. HttpOnly cookies dramatically minimize the client-side attack surface. Distroless or Alpine images reduce the container attack surface to an absolute minimum (no shell, no unnecessary binaries), which will lead to an SCA report with nearly zero vulnerabilities in Trivy.
*   **Development (Cons):** Properly configuring CORS and SameSite cookies for local development environments (between frontend and backend ports) is often error-prone and requires clean environment variables. The lack of a shell in distroless images (backend) makes debugging inside a running pod in the Kubernetes cluster more difficult.