# Security Requirements

This document lists the security requirements that Doctor Holiday **must** implement. They are the fixed reference for the threat model, the implementation, the pipeline and the final documentation.

- **Issue:** [#5 – Define at least 5 mandatory, testable security requirements](https://github.com/jankrus/doctorholiday/issues/5)
- **Grading:** Anforderungen & Architektur → *Security Requirements* (5 points), basis for *Umsetzung Anforderungen* and *Konsistenz Architektur/Umsetzung*. Exam brief §1 asks for at least five.
- **Builds on:** [ADR-001](adr/ADR-001-tech-stack.md), [roles-and-permissions.md](roles-and-permissions.md), [requirements.md](requirements.md) (business rules BR-xx).
- **Used by:** STRIDE analysis ([#8](https://github.com/jankrus/doctorholiday/issues/8)) and the traceability matrix ([#47](https://github.com/jankrus/doctorholiday/issues/47)) reuse the IDs `SR-01` … `SR-11` unchanged. Never renumber; add new requirements at the end.

## How to read this document

- **MUST / SHOULD** follow RFC 2119. A MUST is mandatory and counts as a failed requirement if it is not met; a SHOULD may be dropped with a reason in [deviations.md](../report/deviations.md).
- **ASVS** names the chapters of the OWASP Application Security Verification Standard 4.0 that the requirement maps to.
- **Verification** says how to check the requirement objectively: an automated test, a pipeline gate, a scan or a manifest check. A requirement without a verification is not accepted.
- **Issues** lists the tickets that implement it. The status in the overview is updated when the tickets are merged.
- Verification evidence (reports, run logs) ends up in `evidence/<image>/…` ([#44](https://github.com/jankrus/doctorholiday/issues/44)).

## Overview

| ID | Title | Area | Priority | Status |
| --- | --- | --- | --- | --- |
| [SR-01](#sr-01-strong-authentication-and-session-management) | Strong authentication and session management | App | MUST | In progress ([#73](https://github.com/jankrus/doctorholiday/pull/73) open) |
| [SR-02](#sr-02-authorisation-with-default-deny-and-object-level-checks) | Authorisation with default deny and object-level checks | App | MUST | Open |
| [SR-03](#sr-03-server-side-input-validation-and-safe-data-access) | Server-side input validation and safe data access | App | MUST | Done for the current endpoints (schema [#69](https://github.com/jankrus/doctorholiday/pull/69), validation layer [#13](https://github.com/jankrus/doctorholiday/issues/13)); new routes are checked by test |
| [SR-04](#sr-04-error-handling-and-logging-without-information-leaks) | Error handling and logging without information leaks | App | MUST | Mostly done (health, config, logging [#11](https://github.com/jankrus/doctorholiday/issues/11), error handling [#13](https://github.com/jankrus/doctorholiday/issues/13)); [#22](https://github.com/jankrus/doctorholiday/issues/22) open |
| [SR-05](#sr-05-no-secrets-in-the-repository-or-in-images) | No secrets in the repository or in images | App, CI, K8s | MUST | Open |
| [SR-06](#sr-06-sbom-and-vulnerability-scanning-with-a-blocking-quality-gate) | SBOM and vulnerability scanning with a blocking quality gate | CI/CD | MUST | Open |
| [SR-07](#sr-07-signed-images-verified-before-deployment) | Signed images, verified before deployment | CI/CD | MUST | Open |
| [SR-08](#sr-08-kubernetes-least-privilege) | Kubernetes least privilege | K8s | MUST | Open |
| [SR-09](#sr-09-multi-factor-authentication-with-totp) | Multi-factor authentication with TOTP | App | MUST for staff roles, bonus in the brief | Open |
| [SR-10](#sr-10-security-audit-logging) | Security audit logging | App | MUST | Open |
| [SR-11](#sr-11-http-hardening-against-browser-attacks) | HTTP hardening against browser attacks | App | SHOULD | Open |

## SR-01: Strong authentication and session management

- **Requirement:** The system MUST authenticate every non-public request with a server-side session. Passwords MUST be 12–128 characters and stored only as Argon2id hashes. Login MUST answer wrong e-mail, wrong password and deactivated account identically and in similar time. Login, registration and other credential endpoints MUST be rate limited per client IP and per account. The session cookie MUST be `__Host-dh_session` with `HttpOnly; Secure; SameSite=Strict; Path=/`, the token MUST be random (≥ 128 bit) and stored only as a SHA-256 hash, the session MUST have an idle and an absolute timeout, and the session ID MUST be rotated on every state change and password change. Logout MUST invalidate the session server-side.
- **Rationale:** Spoofing (STRIDE) and credential stuffing are the first attack on a booking system that holds health-related data. Server-side sessions in an `HttpOnly` cookie keep the token out of reach of JavaScript (ADR-001 §2.4).
- **ASVS:** V2 Authentication, V3 Session Management.
- **Business rules:** BR-01, BR-02, BR-03, BR-04, BR-05; see also BR-25 (password reset).
- **Verification:**
  - Integration tests: identical response for wrong e-mail and wrong password; the 6th rapid failed login returns `429`; cookie carries all flags; the old session ID is invalid after login; a logged-out session is rejected.
  - A test asserts that no log line or response body contains a password or hash.
  - `argon2` parameters and password length limits are covered by unit tests.
- **Issues:** [#14](https://github.com/jankrus/doctorholiday/issues/14), [#15](https://github.com/jankrus/doctorholiday/issues/15), [#12](https://github.com/jankrus/doctorholiday/issues/12) (session table), [#61](https://github.com/jankrus/doctorholiday/issues/61), [#66](https://github.com/jankrus/doctorholiday/issues/66), [#75](https://github.com/jankrus/doctorholiday/issues/75)–[#79](https://github.com/jankrus/doctorholiday/issues/79) (rate limits, client IP).

## SR-02: Authorisation with default deny and object-level checks

- **Requirement:** Every endpoint MUST enforce authorisation in the backend; the frontend is never the only check. Access MUST follow the permission matrix in [roles-and-permissions.md](roles-and-permissions.md) and be denied by default for any action not listed. "Own only" actions MUST be checked against the session, never against IDs from the request; foreign objects MUST answer `404`. The admin's access to appointment data MUST additionally be time-limited (TBAC). The first user who logs in while no admin exists MUST become admin atomically, and the last active admin MUST NOT be demoted or deactivated.
- **Rationale:** Elevation of privilege and IDOR are the most common serious flaws in role-based applications. Appointment data is health data (GDPR Art. 9), so need-to-know is a legal topic.
- **ASVS:** V4 Access Control, V1 Architecture (V1.4).
- **Business rules:** BR-04, BR-15, BR-17.
- **Verification:**
  - A role × endpoint test matrix generated from `x-roles` in `backend/openapi.yaml`.
  - A test that fails for every route without an authorisation rule (default deny).
  - IDOR tests: patient A cannot read, cancel or reschedule patient B's appointment (`404`).
  - Concurrency test: two simultaneous first logins produce exactly one admin.
- **Issues:** [#16](https://github.com/jankrus/doctorholiday/issues/16), [#15](https://github.com/jankrus/doctorholiday/issues/15), [#18](https://github.com/jankrus/doctorholiday/issues/18), [#55](https://github.com/jankrus/doctorholiday/issues/55), [#22](https://github.com/jankrus/doctorholiday/issues/22).

## SR-03: Server-side input validation and safe data access

- **Requirement:** The backend MUST validate every request (body, query, path) against a strict schema: unknown fields rejected (`extra="forbid"`), every string bounded, IDs as UUID, closed value sets as enums. Request bodies MUST have a size limit. All database access MUST go through the ORM or bound parameters; building SQL from strings MUST NOT occur. Business invariants that matter for integrity (no overlapping bookings, one admin bootstrap) MUST additionally be enforced by database constraints.
- **Rationale:** Tampering and injection start with unvalidated input. Validation at the type level plus constraints at the database level means a missed code path still cannot corrupt data.
- **ASVS:** V5 Validation, Sanitization and Encoding, V8 Data Protection.
- **Business rules:** BR-09, BR-10, BR-12, BR-20.
- **Verification:**
  - Tests send malformed JSON, unknown fields, over-long strings, wrong types, undeclared query parameters, oversized and non-JSON bodies and expect `422` / `413` / `415` (`backend/tests/test_errors.py`).
  - `backend/tests/test_validation.py` fails for any route whose body, path, query, header or cookie parameters are unbounded or allow unknown fields.
  - Semgrep (SAST) reports no raw-SQL-concatenation pattern.
  - A concurrency test shows that only one of several overlapping bookings succeeds.
  - `redocly lint` passes for `openapi.yaml`.
- **Issues:** [#12](https://github.com/jankrus/doctorholiday/issues/12), [#13](https://github.com/jankrus/doctorholiday/issues/13), [#17](https://github.com/jankrus/doctorholiday/issues/17), [#74](https://github.com/jankrus/doctorholiday/issues/74), [#33](https://github.com/jankrus/doctorholiday/issues/33) (Semgrep).

## SR-04: Error handling and logging without information leaks

- **Requirement:** Errors MUST use one schema with a stable `code`, a short generic `message` and a `requestId`. Responses MUST NOT contain stack traces, SQL, file paths, library names or version numbers. Details MUST be written only to the structured log, which MUST NOT contain passwords, session IDs, tokens, MFA secrets, recovery codes or full request bodies. Interactive API docs and the generated schema MUST be disabled at runtime. Health endpoints MUST return only a status word.
- **Rationale:** Information disclosure helps an attacker map the system; brief §4 asks for "saubere Fehlerbehandlung ohne Informationslecks".
- **ASVS:** V7 Error Handling and Logging, V14 Configuration.
- **Business rules:** BR-21; error conventions in [requirements.md](requirements.md#api-conventions).
- **Verification:**
  - Tests trigger `500` paths (forced exception) and assert the generic body only, with `requestId` equal to `X-Request-Id`, and the stack trace in the log; tests assert the log contains no secrets or submitted values (`backend/tests/test_errors.py`).
  - Unknown paths, wrong methods and framework errors answer in the `Error` schema, never with the framework's `detail`.
  - A test asserts `/docs`, `/redoc` and `/openapi.json` return `404`.
  - Startup test: an invalid configuration logs variable names, never values, and exits with code 1.
- **Issues:** [#11](https://github.com/jankrus/doctorholiday/issues/11) (done), [#13](https://github.com/jankrus/doctorholiday/issues/13), [#22](https://github.com/jankrus/doctorholiday/issues/22).

## SR-05: No secrets in the repository or in images

- **Requirement:** No secret MUST be committed to the repository or baked into an image. All configuration MUST come from environment variables, validated at startup. `.env.example` files MUST contain only placeholders. Kubernetes secrets MUST be generated at deploy time, MUST be mounted only into the containers that need them, and CI secrets (cosign key, registry credentials) MUST live in GitHub encrypted secrets. Every required secret MUST have a documented consumer.
- **Rationale:** Information disclosure through leaked credentials is the cheapest attack. Brief §4 forbids hardcoded secrets and §3e makes found secrets a build breaker.
- **ASVS:** V6 Stored Cryptography (V6.4 secret management), V14 Configuration.
- **Verification:**
  - Gitleaks over the full history reports 0 findings (pipeline gate, #33/#36).
  - `.gitleaks.toml` contains custom rules for `DATABASE_URL`, `MFA_ENCRYPTION_KEY`.
  - Manifest check: secrets in `infrastructure/k8s/` are referenced (`secretKeyRef`), never given as values.
  - `docs/architecture/secrets.md` lists exactly the variables `config.py` requires.
- **Issues:** [#30](https://github.com/jankrus/doctorholiday/issues/30), [#59](https://github.com/jankrus/doctorholiday/issues/59) (`SESSION_SECRET`), [#39](https://github.com/jankrus/doctorholiday/issues/39), [#33](https://github.com/jankrus/doctorholiday/issues/33).

## SR-06: SBOM and vulnerability scanning with a blocking quality gate

- **Requirement:** Every push to `main` MUST run the pipeline: SBOM per image (CycloneDX, Syft), SAST (Semgrep), SCA and image scan (Trivy) and secret scan (Gitleaks). The quality gate MUST fail the run when a secret is found or a finding has CVSS ≥ 7.0 (HIGH or CRITICAL). Dependencies MUST be pinned by lockfile with hashes, GitHub Actions by commit SHA and base images by digest. Reports of every run MUST be kept in `evidence/<image>/`.
- **Rationale:** Supply-chain attacks and known vulnerable dependencies are the main risk of the delivery chain; the brief's quality gate (§3e) demands automatic blocking.
- **ASVS:** V14 Configuration (V14.2 dependency), V10 Malicious Code.
- **Verification:**
  - A pipeline run produces `sbom/`, `sast/`, `sca/` and `secrets/` reports for both images.
  - Gate test: a branch with a planted dummy secret and a branch with a known HIGH vulnerability each fail the gate (kept as evidence).
  - `uv sync --locked` and `npm ci` succeed; a script checks that every `uses:` is a 40-character SHA and every `FROM` has a digest.
- **Issues:** [#31](https://github.com/jankrus/doctorholiday/issues/31), [#32](https://github.com/jankrus/doctorholiday/issues/32), [#33](https://github.com/jankrus/doctorholiday/issues/33), [#36](https://github.com/jankrus/doctorholiday/issues/36), [#44](https://github.com/jankrus/doctorholiday/issues/44), [#46](https://github.com/jankrus/doctorholiday/issues/46), [#28](https://github.com/jankrus/doctorholiday/issues/28).

## SR-07: Signed images, verified before deployment

- **Requirement:** Every image pushed to the registry MUST be signed with cosign (key-based) and carry an SBOM attestation. The pipeline MUST verify the signature against the public key and MUST abort when a signature is missing or invalid. Images MUST be referenced by digest, never by a mutable tag, when they are deployed. The deployment MUST pull from the container registry, not from the build runner.
- **Rationale:** Tampering with an image between build and deployment must be detectable (supply chain integrity, brief §3d/§3e-iii).
- **ASVS:** V10 Malicious Code (V10.3 integrity), V1 Architecture.
- **Verification:**
  - `cosign verify` succeeds in the pipeline; the report is stored in `evidence/<image>/signing/`.
  - Negative test: an unsigned or re-tagged image makes the gate fail.
  - Deployed manifests contain only `image: …@sha256:…`.
- **Issues:** [#35](https://github.com/jankrus/doctorholiday/issues/35), [#34](https://github.com/jankrus/doctorholiday/issues/34), [#36](https://github.com/jankrus/doctorholiday/issues/36), [#43](https://github.com/jankrus/doctorholiday/issues/43), [#45](https://github.com/jankrus/doctorholiday/issues/45) (admission policy, stretch).

## SR-08: Kubernetes least privilege

- **Requirement:** The application MUST run in its own namespace `doctorholiday` with a minimal ServiceAccount per workload (no automounted token unless needed). Every container MUST set `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false` and `capabilities.drop: [ALL]`, and write only to `/tmp`. A NetworkPolicy MUST deny all ingress by default, with explicit allow rules only for ingress → frontend, ingress → backend and backend → database. Containers MUST listen on unprivileged ports and run with a numeric non-root UID.
- **Rationale:** Limits the damage of a compromised container (elevation of privilege, lateral movement); exact settings are prescribed by brief §4.
- **ASVS:** V1 Architecture (V1.2 component separation), V14 Configuration.
- **Verification:**
  - Manifest check in CI (e.g. `kubectl apply --dry-run=server` plus a policy or `kubesec`/`trivy config` scan) for the four security-context fields.
  - `kubectl auth can-i --list --as=system:serviceaccount:doctorholiday:<sa>` shows no extra rights.
  - Network test: a pod without an allow rule cannot reach the backend or the database.
  - Evidence of `make up` and the pod status ends up in the documentation.
- **Issues:** [#37](https://github.com/jankrus/doctorholiday/issues/37), [#38](https://github.com/jankrus/doctorholiday/issues/38), [#39](https://github.com/jankrus/doctorholiday/issues/39), [#41](https://github.com/jankrus/doctorholiday/issues/41), [#28](https://github.com/jankrus/doctorholiday/issues/28), [#42](https://github.com/jankrus/doctorholiday/issues/42).

## SR-09: Multi-factor authentication with TOTP

- **Requirement:** `ADMIN`, `STAFF` and `DOCTOR` MUST use TOTP (RFC 6238) as a second factor; until it is enrolled and verified, their session may only enrol, verify, log out and read its state. `PATIENT` accounts MAY enable it voluntarily. The TOTP secret MUST be stored encrypted with a key from the environment, recovery codes MUST be shown once and stored only as hashes, and MFA verification MUST be rate limited. An admin MUST NOT be able to reset their own MFA.
- **Rationale:** A stolen password alone must not be enough to reach privileged accounts. The brief rates MFA as a bonus (+10 points).
- **ASVS:** V2 Authentication (V2.8 one-time verifiers), V6 Cryptography.
- **Business rules:** BR-05, BR-06, BR-07, BR-16.
- **Verification:**
  - Tests: a staff session in `MFA_ENROLLMENT_REQUIRED` receives `403 MFA_REQUIRED` on every other endpoint; wrong codes return `400` and are rate limited; a recovery code works once.
  - A database check shows `mfa_secret_enc` is not plain text and recovery codes are hashes.
- **Issues:** [#21](https://github.com/jankrus/doctorholiday/issues/21), [#55](https://github.com/jankrus/doctorholiday/issues/55), [#76](https://github.com/jankrus/doctorholiday/issues/76), [#24](https://github.com/jankrus/doctorholiday/issues/24), [#65](https://github.com/jankrus/doctorholiday/issues/65).

## SR-10: Security audit logging

- **Requirement:** Security-relevant events MUST be recorded in an append-only audit log with actor, action, target, client IP, timestamp and outcome: login success and failure, MFA events, bootstrap, invitations, role changes, deactivation, password changes and resets, account deletion, bookings and cancellations, TBAC grants and every access under a grant, settings changes and authorisation denials. Audit events MUST NOT contain passwords, session IDs, tokens, secrets or request bodies. Only an admin MAY read the log.
- **Rationale:** Repudiation: without a trustworthy log, nobody can prove who changed a role or read health data. The log is also the detection mechanism for an unexpected admin.
- **ASVS:** V7 Error Handling and Logging (V7.1, V7.3).
- **Business rules:** BR-19, BR-17.
- **Verification:**
  - Tests: every action from BR-19 produces exactly one event with the expected fields; a denied request produces a `DENIED` event.
  - A test asserts audit rows contain no secret material and that the application database role has no `UPDATE` or `DELETE` on the table.
- **Issues:** [#20](https://github.com/jankrus/doctorholiday/issues/20), [#12](https://github.com/jankrus/doctorholiday/issues/12), [#75](https://github.com/jankrus/doctorholiday/issues/75) (real client IP).

## SR-11: HTTP hardening against browser attacks

- **Requirement:** The system SHOULD set security headers (`Content-Security-Policy` without `unsafe-inline` for scripts, `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store` for personal data, HSTS behind TLS), allow only configured origins in CORS (no wildcard), and protect state-changing requests against CSRF (`SameSite=Strict` plus an `Origin`/`Sec-Fetch-Site` check). The frontend MUST NOT use `dangerouslySetInnerHTML` or `eval` and MUST contain no secrets in the bundle. The ingress MUST terminate TLS.
- **Rationale:** XSS and CSRF are the standard attacks on browser applications; the cookie flags in SR-01 are only one layer.
- **ASVS:** V14 Configuration (V14.4 HTTP security headers), V13 API, V5.
- **Verification:**
  - Tests assert headers on API and static responses; a CORS test rejects a foreign origin.
  - ESLint forbids the unsafe React APIs (already configured); `grep` over `dist/` finds no secret-like strings.
  - `curl -k -I https://…` shows TLS and the headers on the running cluster.
- **Issues:** [#19](https://github.com/jankrus/doctorholiday/issues/19), [#27](https://github.com/jankrus/doctorholiday/issues/27), [#40](https://github.com/jankrus/doctorholiday/issues/40).

## Coverage of the exam topics

| Exam topic (brief) | Requirements |
| --- | --- |
| Threat Modeling | derived in [#8](https://github.com/jankrus/doctorholiday/issues/8) from SR-01 … SR-11 |
| SBOM | SR-06 |
| SAST | SR-03, SR-06 |
| CI/CD pipeline | SR-06, SR-07 |
| Code Signing | SR-07 |
| Secure Coding | SR-01, SR-03, SR-04, SR-11 |
| Least Privilege | SR-02, SR-08 |
| Secret hygiene | SR-05 |
| MFA (bonus) | SR-09 |

## Open points

- The verification of SR-06 and SR-07 needs the pipeline (#31–#36); until then the requirements are only checked by review.
- `SESSION_SECRET` (#59) is still required by `config.py` without a consumer. SR-05 demands that it gets one or is removed.
- Statuses in the overview are maintained by hand; the full mapping SR ↔ STRIDE ↔ implementation ↔ evidence is the traceability matrix in #47.
