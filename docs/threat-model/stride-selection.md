# STRIDE Selection: Three Categories Implemented, Three Justified

The exam brief (§2) asks that only **three** of the six STRIDE categories are implemented or partially implemented, and that the other three are not implemented for a documented reason. This document records the choice, links each selected category to its implementing issues and verification, and justifies the other three.

- **Issue:** [#9 – Select 3 STRIDE categories to implement and justify the other 3](https://github.com/jankrus/doctorholiday/issues/9)
- **Grading:** Threat Modeling → *STRIDE-Bedrohungsanalyse mit Umsetzung* (6 points); brief §2.
- **Builds on:** [stride.md](stride.md) (88 threats TH-01 … TH-88; the column *Sel.* marks the selected threats), [security-requirements.md](../architecture/security-requirements.md).

## 1. Decision

| Category | Decision | One-line reason |
| --- | --- | --- |
| **S**poofing | **Selected**, see [section 2.1](#21-spoofing-s) | Login is mandatory in the brief; stolen identities are the entry point to everything else. |
| **E**levation of privilege | **Selected**, see [section 2.2](#22-elevation-of-privilege-e) | Role model, object-level checks and Kubernetes least privilege are mandatory in the brief and carry the most severe impact. |
| **I**nformation disclosure | **Selected**, see [section 2.3](#23-information-disclosure-i) | Appointment data is health data; the brief names error handling without leaks and no hard-coded secrets. |
| **T**ampering | Not selected, see [section 3.1](#31-tampering-t) | Largest number of threats, but the strong controls belong to other requirements (SR-03, SR-06, SR-07). |
| **R**epudiation | Not selected, see [section 3.2](#32-repudiation-r) | No High-rated threat; only a basic audit log is needed. |
| **D**enial of service | Not selected, see [section 3.3](#33-denial-of-service-d) | Local single-node cluster without internet exposure; real flood protection needs infrastructure out of scope. |

**What "selected" and "not selected" mean here.** *Selected* categories get threat-driven mitigations with a verification method per threat. *Not selected* categories get no dedicated countermeasure beyond what the project builds anyway for other requirements. These controls are honestly named in section 3 and they reduce the risk, but they are not implemented because of this analysis. The residual risk is accepted and explained.

The numbers: 45 of the 88 threats belong to the selected categories and 43 to the others (counts in [stride.md](stride.md#4-summary)).

## 2. Selected categories

For every selected category: threats, implementing issues, how to verify them, and the state today. *Merged* means the issue is closed on `main`; everything else is open or in review.

### 2.1 Spoofing (S)

**Threats:** TH-01, TH-03, TH-05, TH-07, TH-11, TH-23, TH-24, TH-35 are the active ones; TH-09, TH-17 and TH-41 are accepted (operator machine and local scope).

| Threat | Mitigation | Issues | Verification | State |
| --- | --- | --- | --- | --- |
| TH-01, TH-23 Credential stuffing, brute force | Argon2id, 12+ character policy, common-password check, rate limit per IP and account with lockout, generic errors | [#14](https://github.com/jankrus/doctorholiday/issues/14), [#76](https://github.com/jankrus/doctorholiday/issues/76)–[#79](https://github.com/jankrus/doctorholiday/issues/79) | Integration tests: identical response for wrong e-mail and wrong password; 6th failed login returns `429`; no password or hash in logs | In review (PR #73) |
| TH-24 Session hijacking and fixation | Random 256-bit token stored as SHA-256, `__Host-` cookie with `HttpOnly; Secure; SameSite=Strict`, ID rotation, idle and absolute timeout, server-side logout | #14, [#19](https://github.com/jankrus/doctorholiday/issues/19) | Tests: cookie flags, old session ID invalid after login, logged-out session rejected | In review (PR #73) |
| TH-03, TH-05 Takeover of staff and admin accounts | Mandatory TOTP MFA, recovery codes, admin bootstrap in one locked transaction, MFA enrolment forced for the first admin | [#21](https://github.com/jankrus/doctorholiday/issues/21), [#55](https://github.com/jankrus/doctorholiday/issues/55), [#15](https://github.com/jankrus/doctorholiday/issues/15) | Tests: staff session in `MFA_ENROLLMENT_REQUIRED` receives `403` elsewhere; two simultaneous first logins give one admin | Not implemented |
| TH-11 Forged client IP | Ingress sets the client IP, backend trusts only the proxy | [#75](https://github.com/jankrus/doctorholiday/issues/75), [#40](https://github.com/jankrus/doctorholiday/issues/40) | Test: forged `X-Forwarded-For` does not change the rate-limit key | Not implemented |
| TH-35 Impersonated GitHub Action | Actions pinned by commit SHA, Dependabot for actions | [#31](https://github.com/jankrus/doctorholiday/issues/31), [#46](https://github.com/jankrus/doctorholiday/issues/46) | Script check: every `uses:` is a 40-character SHA | Not implemented |
| TH-07 Impersonated developer | Pull request with review of another person, GitHub 2FA | [#48](https://github.com/jankrus/doctorholiday/issues/48) (merged), #31 | Ruleset `protect-main` (enforcement needs GitHub Pro on a private repository) | Partially |

**Merged issues for this category:** [#24](https://github.com/jankrus/doctorholiday/issues/24) (auth screens in the frontend) and [#48](https://github.com/jankrus/doctorholiday/issues/48) (ruleset). The backend issues are not merged yet.

### 2.2 Elevation of privilege (E)

**Threats:** TH-16 (accepted), TH-22, TH-32, TH-33, TH-34, TH-40, TH-46.

| Threat | Mitigation | Issues | Verification | State |
| --- | --- | --- | --- | --- |
| TH-32 IDOR and role bypass | Default-deny RBAC from the permission matrix, object-level checks against the session, foreign objects return `404` | [#16](https://github.com/jankrus/doctorholiday/issues/16), [#22](https://github.com/jankrus/doctorholiday/issues/22) | Role × endpoint test matrix generated from `x-roles`; test that fails for a route without a rule; IDOR tests between two patients | Not implemented |
| TH-33 Bootstrap race, role self-assignment | Locked single-row bootstrap, roles only by invitation or admin endpoint, last-admin protection, `extra="forbid"` | [#15](https://github.com/jankrus/doctorholiday/issues/15), [#18](https://github.com/jankrus/doctorholiday/issues/18), #55 | Concurrency test; test that a `role` field in registration is rejected | Not implemented |
| TH-34 Admin reads health data | 30-minute TBAC grant with a purpose, checked on every request, audited | #55 | Test: `403 ACCESS_GRANT_REQUIRED` without a grant and after expiry | Not implemented |
| TH-22, TH-46 Container escape, ServiceAccount token abuse | `runAsNonRoot`, read-only root filesystem, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, seccomp RuntimeDefault, no mounted API token, no Role bindings | [#28](https://github.com/jankrus/doctorholiday/issues/28), [#37](https://github.com/jankrus/doctorholiday/issues/37), [#38](https://github.com/jankrus/doctorholiday/issues/38) | Manifest check in CI for the four security-context fields; `kubectl auth can-i --list` for the ServiceAccounts | Not implemented |
| TH-40 Over-privileged CI token | Top-level `permissions: {}`, write rights per job only | #31 | Workflow lint: no job has broader permissions than listed | Not implemented |
| TH-16 Controller compromise | Pinned patched ingress version, own namespace, NetworkPolicy; residual risk accepted | [#40](https://github.com/jankrus/doctorholiday/issues/40), [#41](https://github.com/jankrus/doctorholiday/issues/41) | Version pin in the manifest; Trivy scan | Accepted |

**Merged issues for this category: none yet.** [#15](https://github.com/jankrus/doctorholiday/issues/15), [#16](https://github.com/jankrus/doctorholiday/issues/16) and the Kubernetes issues are open. The acceptance criterion "at least one merged implementation issue" is therefore open for this category (see [section 5](#5-open-points)).

### 2.3 Information disclosure (I)

**Threats:** TH-14, TH-20, TH-28, TH-29, TH-38, TH-44, TH-49, TH-53, TH-57, TH-61, TH-65, TH-67, TH-71, TH-74 and the flows that carry secrets, logs or artefacts (TH-67, TH-71, TH-74, TH-76 … TH-88).

| Threat | Mitigation | Issues | Verification | State |
| --- | --- | --- | --- | --- |
| TH-28 Errors leak internals | One error schema with request ID, no docs endpoints, log redaction, no bodies logged, path without query string | [#11](https://github.com/jankrus/doctorholiday/issues/11) (merged), [#13](https://github.com/jankrus/doctorholiday/issues/13) | Tests trigger `500` paths and assert the generic body; test that logs contain no secrets; `/docs`, `/redoc`, `/openapi.json` return `404` | Partially (redaction, request ID, no docs on `main`; central handler open) |
| TH-29 User enumeration | `202` on register, identical `401`, hash computed in every case | #14 | Tests compare response and timing class | In review (PR #73) |
| TH-20 Secrets or internals in the frontend | No `VITE_*` variables, no source maps, error texts from a fixed local map | [#23](https://github.com/jankrus/doctorholiday/issues/23) (merged), [#27](https://github.com/jankrus/doctorholiday/issues/27) | `grep` over `dist/`; ESLint rules | Partially |
| TH-57, TH-38, TH-65, TH-80, TH-84 Secrets in the repository, logs or CI | `.env.example` placeholders, push protection, Gitleaks over the full history, secrets scoped to the sign job | [#30](https://github.com/jankrus/doctorholiday/issues/30), [#33](https://github.com/jankrus/doctorholiday/issues/33), [#35](https://github.com/jankrus/doctorholiday/issues/35) | Gitleaks: 0 findings on the full history (pipeline gate); manifest check: only `secretKeyRef` | Partially (GitHub scanning on) |
| TH-44, TH-53, TH-76, TH-77, TH-86 Secrets in the cluster | Generated at deploy time, mounted only where needed, minimal RBAC, startup validation without printing values | #30, [#37](https://github.com/jankrus/doctorholiday/issues/37), [#39](https://github.com/jankrus/doctorholiday/issues/39), [#42](https://github.com/jankrus/doctorholiday/issues/42) | Manifest check; test that invalid configuration logs names only | Partially (validation on `main`) |
| TH-49 PHI and hashes in the database | Argon2id hashes, TOTP secrets encrypted, separate `credentials` table, data minimisation | [#12](https://github.com/jankrus/doctorholiday/issues/12), #21 | Test: DB columns are not plain text; code review of the table layout | In review (PR #69) |
| TH-67, TH-14 Traffic in transit | HTTPS only, HSTS, `Secure` cookie, `no-store` for personal data, TLS key as a Secret | #40, #19 | `curl -k -I` shows TLS and headers on the running cluster | Not implemented |
| TH-71, TH-74 Plain traffic inside the cluster | NetworkPolicy default deny; no TLS inside (accepted) | [#41](https://github.com/jankrus/doctorholiday/issues/41) | Network test: pod without allow rule cannot reach backend or database | Accepted |
| TH-61, TH-81, TH-82 Private artefacts | Private package, read-only `imagePullSecret`, no secrets in layers | [#28](https://github.com/jankrus/doctorholiday/issues/28), [#34](https://github.com/jankrus/doctorholiday/issues/34) | Trivy image scan; layer inspection | Not implemented |
| TH-87, TH-88 Verbose health output, secrets in logs | Status word only on probes; structured logs with redaction, no bodies, path without query string | #11 | Tests on `/healthz` and `/readyz` bodies; test that logs contain no secrets | Implemented |

**Merged issues for this category:** [#11](https://github.com/jankrus/doctorholiday/issues/11) (backend skeleton), [#23](https://github.com/jankrus/doctorholiday/issues/23) (frontend skeleton) and [#48](https://github.com/jankrus/doctorholiday/issues/48) (secret scanning with push protection).

## 3. Justification for the three other categories

The three remaining categories are not implemented as dedicated, threat-driven countermeasures. For each: reason, what is covered anyway, residual risk, and what a production system would add. The controls that exist for other requirements are named so that the analysis does not claim more or less than the project does.

### 3.1 Tampering (T)

**Reason.** Tampering has the largest number of threats (28, tied with Denial of service), but the strongest countermeasures belong to other graded topics: image signing and the quality gate are CI/CD requirements (SR-06, SR-07), and SQL injection protection is part of the general secure-coding requirement (SR-03). Adding a separate threat-driven programme (integrity protection of data at rest, mutual TLS inside the cluster, tamper-evident storage) needs infrastructure that does not fit a single-node local cluster and would add components (service mesh, key management) without improving what the brief examines.

**Covered anyway (not counted as implementation of this category):**

| Threat | Control | Requirement |
| --- | --- | --- |
| TH-25, TH-73 | Pydantic validation, ORM with bound parameters, Semgrep rule against SQL from strings | SR-03 |
| TH-47 | Database constraints (exclusion constraint, check constraints), separate DB role | SR-03 |
| TH-59, TH-81, TH-82, TH-83 | Digest references, cosign signature, verification before deploy | SR-07 |
| TH-18, TH-36 | Lockfiles, SBOM, SCA, reviewed workflow changes | SR-06 |
| TH-26 | `SameSite=Strict` and an `Origin` check | SR-11 |

**Residual risk.** A compromised backend can change data in the database it may write to; a compromised pod can alter plain in-cluster traffic (TH-69, TH-70). Rated Medium for a local demo. **In production:** mTLS or a service mesh, row-level integrity checks for security-critical tables, immutable registry tags and admission-time signature enforcement ([#45](https://github.com/jankrus/doctorholiday/issues/45)).

### 3.2 Repudiation (R)

**Reason.** None of the 15 repudiation threats is rated High. The application needs only a basic audit log for its own functions (admin audit view, TBAC grants, role changes), which [#20](https://github.com/jankrus/doctorholiday/issues/20) builds as part of the admin features. A forensic-grade, tamper-evident log (hash chain, write-once storage, trusted time stamps, central collection) needs a logging platform that is out of scope for the exam and for one practice running locally.

**Covered anyway:**

| Threat | Control | Requirement |
| --- | --- | --- |
| TH-02, TH-04, TH-06, TH-27 | Audit events with actor, action, target, IP and outcome (BR-19), app role cannot change them | SR-10 |
| TH-08, TH-56 | Git history, pull request records | SR-06 |
| TH-13, TH-37 | Backend access log with request ID; run logs and evidence per pipeline run | SR-06, SR-10 |

**Residual risk.** An attacker with database administrator rights could alter audit rows; actions on the cluster and the operator's machine leave no audit trail (TH-10, TH-43, TH-52, accepted). Rated Low to Medium. **In production:** append-only or externally shipped logs, Kubernetes audit policy, signed log entries.

### 3.3 Denial of service (D)

**Reason.** Availability matters for a booking system, but the deployment is a local single-node kind cluster, not reachable from the internet (assumption A4), and the brief names no availability requirement. Real protection against network-level floods needs infrastructure the project does not have: a CDN or WAF, autoscaling, redundant replicas, a replicated database. Spending the limited time on those would not be examined and would pull effort from the selected categories.

**Covered anyway:**

| Threat | Control | Requirement |
| --- | --- | --- |
| TH-30, TH-72 | Rate limits on credential endpoints (built for Spoofing), bounded password length, body size limit | SR-01, SR-03 |
| TH-31 | At most 5 open appointments per patient and per guest phone | SR-02 |
| TH-45 | Resource requests and limits, restarting probes | SR-08 |
| TH-50, TH-75 | Pool limits, bookings serialised per doctor | SR-03 |
| TH-15, TH-68 | Ingress rate-limit annotations | SR-11 |

**Residual risk.** A determined flood or a failed node makes the application unavailable until it restarts; the single database is a single point of failure. Rated Low to Medium for a local demo. **In production:** WAF and rate limiting at the edge, horizontal scaling with several replicas, a replicated database, load tests and alerting.

## 4. Consistency with stride.md

- The column *Sel.* in [stride.md](stride.md) marks every threat as selected (*yes*) or not selected (*no*). A threat with several categories counts as selected if one of them is S, E or I. Result: 45 selected, 43 not selected.
- The *Status* column keeps the factual state on `main` for every threat. It is *not* set to *Accepted* just because the category is not selected: SQL injection (TH-25) is partially mitigated even though Tampering is not selected, and the table says so.
- Accepted risks that apply to both groups (plain in-cluster traffic, no etcd or volume encryption, no Kubernetes audit log) are listed in the open points of stride.md and have to be named under brief §5e.

## 5. Open points

- **Merged implementation issues.** The acceptance criterion of #9 asks for at least one merged implementation issue per selected category. Today this holds for Information disclosure ([#11](https://github.com/jankrus/doctorholiday/issues/11), [#23](https://github.com/jankrus/doctorholiday/issues/23), [#48](https://github.com/jankrus/doctorholiday/issues/48)) and, only on the frontend side, for Spoofing ([#24](https://github.com/jankrus/doctorholiday/issues/24)). It does not hold yet for Elevation of privilege. It is met as soon as the backend authentication (PR #73) and authorisation ([#16](https://github.com/jankrus/doctorholiday/issues/16)) land. This is why the pull request references #9 without closing it.
- **Counts and statuses** change with every merge. The authoritative mapping from requirement to threat, implementation and evidence is the traceability matrix ([#47](https://github.com/jankrus/doctorholiday/issues/47)).
- **Presentation.** The justification in section 3 is the answer to the examiner's question why three categories were left out; it names the controls that exist anyway on purpose.
