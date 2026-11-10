# STRIDE Threat Analysis

STRIDE analysis of Doctor Holiday for every DFD element and every data flow that crosses a trust boundary ([system-model.md](system-model.md)). Each threat names its mitigation, the security requirement it belongs to and its implementation status. It drives the choice of the three implemented STRIDE categories ([#9](https://github.com/jankrus/doctorholiday/issues/9)) and the traceability matrix ([#47](https://github.com/jankrus/doctorholiday/issues/47)).

- **Issue:** [#8 – Perform the STRIDE analysis per component and boundary-crossing flow](https://github.com/jankrus/doctorholiday/issues/8)
- **Grading:** Threat Modeling → *STRIDE-Bedrohungsanalyse mit Umsetzung* (6 points); brief §2.
- **Inputs:** elements E1–E5, P1–P5, DS1–DS5 and flows DF1–DF17 from [system-model.md](system-model.md); requirements SR-01 … SR-11 from [security-requirements.md](../architecture/security-requirements.md).
- **Table format:** the columns of the lecture (Bedrohung, Beispielangriff, Voraussetzungen, Gegenmaßnahmen, Status), extended by ID, element, risk, requirement and issue.

## 1. Method

**STRIDE per element.** Which categories apply depends on the element type:

| Element type | Categories analysed | Reason |
| --- | --- | --- |
| External entity (E) | S, R | An outside actor can be impersonated or deny what it did. |
| Process (P) | S, T, R, I, D, E | Code can be attacked in every way. |
| Data store (DS) | T, R, I, D | A store has no identity of its own and holds no privileges. |
| Data flow (DF) | T, I, D | Spoofing, repudiation and privilege escalation are threats against the endpoints, so they appear in the rows of the processes and entities the flow connects. |

Section 3 shows that every applicable pair of element and category is covered by at least one threat (or states why none exists).

**Sel.** (selected) says whether the threat belongs to one of the three STRIDE categories that the team implements and verifies on purpose: *yes* if any of its categories is Spoofing, Elevation of privilege or Information disclosure. The decision and the justification for the other three categories are in [stride-selection.md](stride-selection.md).

**Risk.** *Risk* is the inherent risk before mitigation: likelihood and impact are each rated Low, Medium or High and combined (H+H, H+M, M+H = **High**; M+M, H+L, L+H = **Medium**; everything else = **Low**). The attacker model: an anonymous internet-style attacker through the browser, a registered but malicious user, a compromised developer account or dependency, and a user with a stolen device. The operator's machine and GitHub as a platform are trusted (assumptions A1, A2 in the system model).

**Status** is the state on `main` when this document was written:

| Status | Meaning |
| --- | --- |
| Implemented | Merged to `main` and in effect. |
| Partially | Part of the mitigation exists, or it exists in an open pull request (named in the issue column), or it is configured but not enforced. |
| Not implemented | Planned; the issue is open. |
| Accepted | Residual risk is accepted with a reason (local demo cluster, out of scope, cost). Listed again in [#9](https://github.com/jankrus/doctorholiday/issues/9) and in the final documentation under brief §5e. |

Status values change with every merged pull request; the authoritative mapping to evidence is the traceability matrix in [#47](https://github.com/jankrus/doctorholiday/issues/47).

## 2. Threat tables

Abbreviations: `req.` precondition, `Impl.` Implemented, `Part.` Partially, `Not impl.` Not implemented. Issue numbers are [#n](https://github.com/jankrus/doctorholiday/issues).

### 2.1 External entities (S, R)

| ID | Element | STRIDE | Sel. | Bedrohung | Beispielangriff | Voraussetzungen | Gegenmaßnahmen | SR | Risk | Status | Issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TH-01 | E1 Patient | S | yes | Attacker acts as a patient and reads or cancels their appointments | Credential stuffing with leaked passwords; stolen session cookie | Reachable login, weak or reused password | Argon2id, 12+ char policy and common-password check, rate limit per IP and per account with lockout, generic login errors, `HttpOnly; Secure; SameSite=Strict` cookie, optional MFA | SR-01, SR-09 | High | Part. (PR #73 open) | #14, #21, #76 |
| TH-02 | E1 Patient | R | no | Patient denies having booked or cancelled an appointment | "I never cancelled that" | No record of who acted | Audit event for every booking, reschedule and cancellation with actor and time; `booked_by_id`, `cancelled_by_id` columns | SR-10 | Low | Not impl. | #20, #17 |
| TH-03 | E2 Staff / Doctor | S | yes | Attacker takes over a staff or doctor account | Phishing of a staff password; password reuse | Password known | Mandatory TOTP MFA, recovery codes, rate-limited MFA verification, admin-invited accounts only | SR-09, SR-01 | High | Not impl. | #21, #55, #76 |
| TH-04 | E2 Staff / Doctor | R | no | Staff denies cancelling an appointment, moving it or issuing a password-reset code | "Not me" after a patient complaint | Shared accounts, no log | Per-user accounts, audit events with actor, target and outcome for A10, A30, A34 | SR-10 | Medium | Not impl. | #20, #61 |
| TH-05 | E3 Admin | S | yes | Attacker becomes admin (first-login rule) or steals an admin session | Registers and logs in first after deployment; session theft | First login after a deployment or database reset; stolen cookie | Bootstrap in one locked transaction, MFA enrolment forced immediately, residual risk documented, operator logs in right after `make up` | SR-02, SR-09 | High | Not impl. | #15, #21 |
| TH-06 | E3 Admin | R | no | Admin denies a role change, deactivation or access to appointment data | "I did not read patient data" | Admin acts without trace | Audit events for role changes and every access under a TBAC grant, grant expiry event; admin cannot edit the log | SR-10, SR-02 | Medium | Not impl. | #20, #55 |
| TH-07 | E4 Developer | S | yes | Attacker pushes as a developer | Stolen GitHub token or SSH key; commit with a forged author | Developer account compromised | Pull request with review of another person, 2FA on GitHub accounts, push protection, short-lived tokens | SR-06 | High | Part. (ruleset configured, not enforced on Free private repos; Pro pending) | #31 |
| TH-08 | E4 Developer | R | no | Developer denies a malicious or faulty change | "I never merged that" | Direct pushes, squashed history | Branch ruleset (PR only), Git history, pipeline evidence per commit SHA | SR-06 | Low | Part. (same as TH-07) | #44 |
| TH-09 | E5 Operator | S | yes | Someone else runs `make up` or `kubectl` on the operator's machine | Unlocked laptop | Physical or local access | Out of scope (A1): the host is trusted; cluster API is local only | – | Low | Accepted | – |
| TH-10 | E5 Operator | R | no | Operator actions in the cluster leave no audit trail | Secrets rotated or manifests changed by hand | No K8s audit log in kind | Changes go through `make up` and the repository; no cluster audit policy for the demo | – | Low | Accepted | #42 |

### 2.2 Processes (S, T, R, I, D, E)

| ID | Element | STRIDE | Sel. | Bedrohung | Beispielangriff | Voraussetzungen | Gegenmaßnahmen | SR | Risk | Status | Issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TH-11 | P1 ingress-nginx | S | yes | Client spoofs its IP or host so rate limits and audit are wrong or bypassed | Forged `X-Forwarded-For` header | Backend trusts the header blindly | Ingress overwrites the header; backend reads the real client IP only from the trusted proxy | SR-01, SR-10 | Medium | Not impl. | #75, #40 |
| TH-12 | P1 ingress-nginx | T | no | Ingress configuration or controller version is tampered with or vulnerable | Annotation injection; unpatched controller CVE | Write access to Ingress objects; old version | Pinned upstream manifest with explicit version, only operator and pipeline apply manifests, Trivy scan of the image | SR-06, SR-08 | Medium | Not impl. | #40, #33 |
| TH-13 | P1 ingress-nginx | R | no | Edge requests are not logged | Attack leaves no trace at the edge | Default log level off | Ingress access log plus backend access log with request ID | SR-10 | Low | Part. (backend access log with request ID is on `main`) | #40, #11 |
| TH-14 | P1 ingress-nginx | I | yes | Private TLS key or version banner leaks; plain HTTP is served | TLS key in the repository; downgrade to HTTP | Key committed or HTTP allowed | Key generated at `make up` and stored as a Secret, redirect to HTTPS, HSTS, server tokens off | SR-05, SR-11 | Medium | Not impl. | #40, #30 |
| TH-15 | P1 ingress-nginx | D | no | Request flood or slow requests take the entry point down | Slowloris, many large bodies | Reachable port 443 | Rate-limit annotations, body-size and timeout limits, ports mapped to localhost only | SR-11 | Low | Not impl. | #40 |
| TH-16 | P1 ingress-nginx | E | yes | Compromised controller reads secrets of other namespaces | Controller CVE leads to cluster-wide secret read | Vulnerable controller version | Pinned patched version, own namespace, NetworkPolicy; residual risk accepted for a local cluster | SR-08 | Medium | Accepted | #40, #41 |
| TH-17 | P2 Frontend | S | yes | Fake copy of the frontend collects credentials | Look-alike site on another host | Users follow a link | Only the cluster host is served; `__Host-` cookie is bound to the exact host; local scope | SR-11 | Low | Accepted | – |
| TH-18 | P2 Frontend | T | no | Served bundle is modified (malicious dependency, tampered image) or XSS injects script | Compromised npm package; stored XSS | Dependency compromised; unsafe rendering | `package-lock.json`, `npm ci`, SCA and SBOM, image signing, no `dangerouslySetInnerHTML` or `eval` (ESLint), CSP | SR-06, SR-07, SR-11 | High | Part. (lockfile and ESLint rules on `main`) | #27, #32, #33, #35 |
| TH-19 | P2 Frontend | R | no | Frontend actions cannot be traced | – | – | The SPA holds no state or authority; every action is an API call that the backend audits (SR-10) | SR-10 | Low | Accepted | #20 |
| TH-20 | P2 Frontend | I | yes | Secrets or internals end up in the bundle or error pages | Source maps, `VITE_*` secrets, verbose server messages | Build reads env variables | No `VITE_*` variables, `sourcemap: false`, server error texts never shown (fixed local map), nginx without version | SR-05, SR-04 | Medium | Part. (no `VITE_*` and error map on `main`; nginx hardening planned) | #27, #28 |
| TH-21 | P2 Frontend | D | no | Static file server overloaded | Many requests for the bundle | Reachable ingress | nginx serves static files cheaply, resource limits, ingress rate limit | SR-11, SR-08 | Low | Not impl. | #38, #40 |
| TH-22 | P2 Frontend | E | yes | Container escape from the nginx pod | Exploit in nginx or image | Vulnerable image, root user | `nginx-unprivileged`, UID non-root, read-only root FS, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, seccomp RuntimeDefault | SR-08 | Medium | Not impl. | #28, #38 |
| TH-23 | P3 Backend | S | yes | Credential stuffing or brute force against login, MFA, invitation or reset endpoints | Automated login attempts with leaked lists | Reachable `/api/v1/auth/*` | Rate limit per IP and account with temporary lockout, Argon2id, generic errors, rate limits on MFA, invitation, reset and re-authentication | SR-01 | High | Part. (login and register limited in PR #73) | #14, #76–#79 |
| TH-24 | P3 Backend | S | yes | Session hijacking or fixation | Stolen cookie; attacker plants a known session ID | XSS, network sniffing, shared device | Random 256-bit token stored as SHA-256, `__Host-` cookie with `HttpOnly; Secure; SameSite=Strict`, ID rotation on login and state change, idle and absolute timeout, server-side logout | SR-01, SR-11 | High | Part. (PR #73 open) | #14, #19 |
| TH-25 | P3 Backend | T | no | Manipulated or malicious input: injection, mass assignment, oversized payloads | SQL injection; extra field `role: ADMIN` in registration | Reachable API | Pydantic `extra="forbid"`, bounded fields and enums, size limit, ORM with bound parameters, Semgrep rule against SQL from strings, DB constraints as last guard | SR-03 | High | Part. (Semgrep rule and data layer in PR #69; central validation open) | #12, #13, #33 |
| TH-26 | P3 Backend | T | no | Cross-site request forgery changes state | Malicious page submits a booking or role change | Victim logged in | `SameSite=Strict`, `Origin` / `Sec-Fetch-Site` check on state-changing requests, no wildcard CORS | SR-11 | Medium | Not impl. | #19 |
| TH-27 | P3 Backend | R | no | Security events are not recorded or can be altered | Role change without a trace | No audit log | Append-only audit log of BR-19 events with actor, target, IP, outcome; app DB role cannot update or delete it | SR-10 | Medium | Not impl. | #20 |
| TH-28 | P3 Backend | I | yes | Errors or logs leak internals or secrets | Stack trace with SQL; password in a log line | Unhandled exception; debug logging | Uniform error schema with request ID, no docs endpoints, log redaction, config errors name variables only, no bodies logged | SR-04 | High | Part. (error schema and handler open; log redaction, request ID, no docs on `main`) | #11, #13, #22 |
| TH-29 | P3 Backend | I | yes | User enumeration through different responses or timing | Register or login reveals whether an e-mail exists | Differences in response or time | `202` on register for existing e-mail, identical `401`, hash computed in every case, identical reset error | SR-01 | Medium | Part. (register and login in PR #73) | #14, #61 |
| TH-30 | P3 Backend | D | no | Resource exhaustion: Argon2id cost, login flood, huge requests | Thousands of parallel logins | Reachable endpoints | Rate limits, bounded password length (128), body size limit, 31-day availability window, sync endpoints in a bounded thread pool, resource limits in K8s | SR-01, SR-03, SR-08 | Medium | Part. (PR #73, limits planned) | #14, #13, #38 |
| TH-31 | P3 Backend | D | no | Booking abuse blocks slots | Script books all free times | Registered account | Maximum 5 open appointments per patient and per guest phone, rate limits, audit of bookings, staff can cancel | SR-02, SR-10 | Medium | Not impl. | #17, #20 |
| TH-32 | P3 Backend | E | yes | Horizontal or vertical privilege escalation | IDOR: read another patient's appointment; patient calls an admin endpoint | Valid session | Default-deny RBAC from the permission matrix, object-level checks against the session, foreign objects return `404`, role × endpoint test matrix | SR-02 | High | Not impl. | #16, #22 |
| TH-33 | P3 Backend | E | yes | Admin bootstrap race or role self-assignment | Two simultaneous first logins both become admin; `role` field in a request | First login after deployment | Single-row lock `SELECT … FOR UPDATE` in one transaction, roles only via invitation and admin endpoint, last-admin protection | SR-02 | High | Not impl. | #15, #18, #55 |
| TH-34 | P3 Backend | E | yes | Admin reads health data without need | Admin lists all appointments | Admin account (or stolen admin session) | TBAC: 30-minute grant with a stated purpose, checked on every request, audit of grant and each access | SR-02, SR-10 | Medium | Not impl. | #55, #20 |
| TH-35 | P4 Pipeline | S | yes | A third-party action or dependency impersonates a trusted one | Typosquatted action; moved tag | Unpinned actions | Actions pinned by full commit SHA, minimal workflow permissions, Dependabot for actions | SR-06 | High | Not impl. | #31, #46 |
| TH-36 | P4 Pipeline | T | no | Workflow, scan configuration or build inputs are tampered with so findings are hidden | PR weakens the quality gate; poisoned dependency | Write access or unreviewed change | Review for changes to `.github/` and `scripts/`, gate logic in a versioned script with tests, gate demo on throwaway branches as evidence | SR-06, SR-07 | High | Not impl. | #31, #36 |
| TH-37 | P4 Pipeline | R | no | A run cannot be attributed or reproduced | Image of unknown origin | No logs or provenance | Run logs and reports stored as evidence per run, build provenance, SBOM per image | SR-06 | Low | Not impl. | #34, #44 |
| TH-38 | P4 Pipeline | I | yes | Signing key or token leaks through logs or a malicious step | `echo` of a secret; untrusted code in a job with secrets | Secrets exposed to broad jobs | Secrets only in the sign job, no secret printing, no `pull_request_target` with secrets, Gitleaks over history, short-lived `GITHUB_TOKEN` | SR-05, SR-07 | High | Not impl. | #30, #33, #35 |
| TH-39 | P4 Pipeline | D | no | Runner time exhausted, pipeline blocked | Many runs triggered | Public PRs or loops | `concurrency` group, `paths-ignore` for the evidence commit, private repository | SR-06 | Low | Not impl. | #31 |
| TH-40 | P4 Pipeline | E | yes | Over-privileged token or job takes over the repository or registry | Token with `contents: write` used by a compromised step | Broad default permissions | Top-level `permissions: {}`, write rights per job only (`packages: write` push job, `contents: write` evidence job) | SR-06 | High | Not impl. | #31 |
| TH-41 | P5 API server + kubelet | S | yes | Stolen kubeconfig used to call the API | Kubeconfig file copied from the operator machine | Local access | Local-only API endpoint, kubeconfig stays on the operator machine (A1) | SR-08 | Low | Accepted | #42 |
| TH-42 | P5 API server + kubelet | T | no | Unreviewed or malicious manifests are applied | `kubectl apply` of a changed manifest; unsigned image | Operator or pipeline credentials | Manifests only from the repository, images by digest, signature verified before `apply`, quality gate before deploy | SR-07, SR-06 | High | Not impl. | #38, #36, #43 |
| TH-43 | P5 API server + kubelet | R | no | Cluster API calls are not audited | Secret read without a record | No audit policy | Not enabled in kind for the demo | – | Low | Accepted | – |
| TH-44 | P5 API server + kubelet | I | yes | Secrets read through the API or from node and container logs | `kubectl get secret -o yaml`; secret in a log | Cluster access | Secrets only via `secretKeyRef`, no secret logging, minimal ServiceAccounts with no RBAC | SR-05, SR-08 | Medium | Not impl. | #30, #37 |
| TH-45 | P5 API server + kubelet | D | no | Node resources exhausted by one pod | Memory leak or fork bomb | No limits | Requests and limits on every container, probes restart hung pods | SR-08 | Medium | Not impl. | #38 |
| TH-46 | P5 API server + kubelet | E | yes | Pod escape or ServiceAccount token abuse | Compromised backend uses the mounted token against the API | Token mounted, root, host access | `automountServiceAccountToken: false`, no Role bindings, `runAsNonRoot`, read-only root FS, no privilege escalation, `capabilities.drop: [ALL]`, seccomp RuntimeDefault | SR-08 | High | Not impl. | #37, #38 |

### 2.3 Data stores (T, R, I, D)

| ID | Element | STRIDE | Sel. | Bedrohung | Beispielangriff | Voraussetzungen | Gegenmaßnahmen | SR | Risk | Status | Issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TH-47 | DS1 PostgreSQL | T | no | Data or schema is changed outside the application rules | Direct SQL after a backend compromise; double booking | Network access or injected SQL | Exclusion and check constraints, separate non-superuser DB role, NetworkPolicy (only backend), migrations run by a controlled step | SR-03, SR-08 | High | Part. (constraints and migrations in PR #69) | #12, #41, #39 |
| TH-48 | DS1 PostgreSQL | R | no | Audit log rows are altered or deleted | Admin or attacker erases evidence | App role may update the table | Append-only table: app role has `INSERT` and `SELECT` only on `audit_events` | SR-10 | Medium | Not impl. | #20, #12 |
| TH-49 | DS1 PostgreSQL | I | yes | Database dump or volume exposes PHI and hashes | Stolen PVC data; backup file copied | Host or volume access | Argon2id hashes, TOTP secrets encrypted with `MFA_ENCRYPTION_KEY`, credentials in a separate table, no Ingress, data minimisation (reason categories, no free text); no encryption at rest on the kind volume (accepted) | SR-01, SR-05 | High | Part. (accepted for volume encryption) | #12, #39, #21 |
| TH-50 | DS1 PostgreSQL | D | no | Database unavailable: connection exhaustion, deadlocks, disk full | Many connections; concurrent bookings deadlock | Load or bad code | Pool limits and timeouts, readiness probe, serialised bookings per doctor, PVC size | SR-03, SR-08 | Medium | Part. (serialised bookings in PR #69) | #74, #39 |
| TH-51 | DS2 Kubernetes Secrets | T | no | A secret is replaced with an attacker's value | `kubectl apply` of a secret | API write access | Secrets generated by `make up`, never overwritten, only the operator and the deploy job can write | SR-05 | Medium | Not impl. | #30, #42 |
| TH-52 | DS2 Kubernetes Secrets | R | no | Secret changes are not recorded | – | No cluster audit | Not enabled in kind (see TH-43) | – | Low | Accepted | – |
| TH-53 | DS2 Kubernetes Secrets | I | yes | Secrets are readable by anyone with API access; stored base64 and unencrypted in etcd | `kubectl get secret`; etcd file on the node | Cluster access (A1) | Minimal RBAC, no secret in manifests or images, mounted only into needed containers; no etcd encryption in kind (accepted) | SR-05, SR-08 | Medium | Accepted (etcd), Not impl. (RBAC) | #30, #37 |
| TH-54 | DS2 Kubernetes Secrets | D | no | A deleted or malformed secret stops the pods | `MFA_ENCRYPTION_KEY` in the wrong format | Operator error | Backend validates configuration at startup and exits with variable names only; `make up` generates the right format | SR-04, SR-05 | Low | Part. (startup validation on `main`) | #30, #42 |
| TH-55 | DS3 Git repository | T | no | Malicious commit reaches `main`, history is rewritten | Force push; unreviewed merge | Write access, no enforcement | Ruleset: PR with review, no force push, no deletion; Pro plan needed for enforcement on private repos; four-eyes policy | SR-06 | High | Part. | #31 |
| TH-56 | DS3 Git repository | R | no | Changes cannot be attributed | Squash or rewrite hides the author | Missing history | Git history, PR records, ruleset forbids history rewrite | SR-06 | Low | Part. (same as TH-55) | – |
| TH-57 | DS3 Git repository | I | yes | Secrets or keys are committed | `.env` or a private key in a commit | Developer error | `.gitignore`, `.env.example` placeholders, GitHub secret scanning with push protection (enabled), Gitleaks in pipeline, pre-commit hook | SR-05 | High | Part. (GitHub scanning and `.gitignore` on `main`) | #30, #33 |
| TH-58 | DS3 Git repository | D | no | Repository or branch deleted | Accidental deletion | Admin rights | Ruleset blocks branch deletion; local clones and a submission ZIP of the repository | SR-06 | Low | Part. | – |
| TH-59 | DS4 GHCR | T | no | Image or tag replaced after signing | Re-pushed mutable tag; poisoned layer | Registry write access | Digest references only, cosign signature verified before deploy, no `latest` | SR-07 | High | Not impl. | #34, #35, #36 |
| TH-60 | DS4 GHCR | R | no | Origin of an image is unclear | Unknown pusher | No provenance | Build provenance and SBOM attestation, signature tied to the key, run log as evidence | SR-07, SR-06 | Low | Not impl. | #34, #35 |
| TH-61 | DS4 GHCR | I | yes | Private images or SBOMs readable by others | Leaked pull token | Token exposed | Private package, `imagePullSecret` with read-only access, no secrets in layers | SR-05, SR-06 | Medium | Not impl. | #28, #34 |
| TH-62 | DS4 GHCR | D | no | Registry outage blocks deployment | GHCR unavailable | Third-party dependency | Fallback: image loaded from the `.tar` of the submission package; images cached in kind | SR-07 | Low | Accepted | #42, #51 |
| TH-63 | DS5 GitHub secrets | T | no | Signing secret replaced | Attacker with repo admin rights swaps the key | Repo admin compromise | Public key `cosign.pub` committed and reviewed, verify step fails on a different key | SR-07 | Medium | Not impl. | #35 |
| TH-64 | DS5 GitHub secrets | R | no | Secret access cannot be proven | – | – | GitHub keeps run and settings audit logs (platform, A2) | – | Low | Accepted | – |
| TH-65 | DS5 GitHub secrets | I | yes | Signing key stolen | Malicious workflow prints or uploads the key | Workflow change reaches `main` | Review of workflow changes, key only in the sign job, passphrase as a second secret, rotation approach in `secrets.md` | SR-05, SR-07 | High | Not impl. | #30, #35 |
| TH-66 | DS5 GitHub secrets | D | no | Secret deleted, signing breaks | Accidental removal | Repo admin | Gate fails closed (no signature, no deploy); key backup with the team | SR-07 | Low | Not impl. | #35, #36 |

### 2.4 Data flows crossing trust boundaries (T, I, D)

| ID | Flow | STRIDE | Sel. | Bedrohung | Beispielangriff | Voraussetzungen | Gegenmaßnahmen | SR | Risk | Status | Issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TH-67 | DF1 Browser → P1 | T, I | yes | Credentials, cookie and PHI intercepted or modified on the way | Man in the middle; downgrade to HTTP | Plain HTTP, untrusted network | HTTPS only with redirect, HSTS, `Secure` `__Host-` cookie, `Cache-Control: no-store` for personal data; self-signed certificate (users trust it manually) | SR-11, SR-01 | High | Not impl. | #40, #19 |
| TH-68 | DF1 Browser → P1 | D | no | Flood of requests at the entry | HTTP flood | Reachable port | Ingress rate limits, localhost-only mapping | SR-11 | Low | Not impl. | #40 |
| TH-69 | DF2 P1 → P2 | T, D | no | Static files altered or served slowly inside the cluster | Compromised pod answers instead of P2 | Pod in the cluster | NetworkPolicy allows only ingress → frontend, content is public so confidentiality is not at stake, bundle integrity by signed image | SR-08, SR-07 | Low | Not impl. | #41 |
| TH-70 | DF3 P1 → P3 | T | no | Request manipulated between ingress and backend (smuggling, header injection) | Crafted `Transfer-Encoding`; forged identity headers | Other pods can reach the backend | NetworkPolicy, backend ignores identity headers (session from cookie only), validation, body limit | SR-03, SR-08 | Medium | Not impl. | #41, #13 |
| TH-71 | DF3 P1 → P3 | I | yes | PHI and cookie readable inside the cluster (plain HTTP) | Sniffing from a compromised pod | Pod in the same network | NetworkPolicy default deny; no TLS inside the cluster (accepted for a single-node local cluster; production would use a mesh or mTLS) | SR-08 | Medium | Accepted | #41 |
| TH-72 | DF3 P1 → P3 | D | no | API flooded through the ingress | Many requests to expensive endpoints | Reachable ingress | Rate limits at ingress and in the backend, request size limits | SR-01, SR-03 | Medium | Part. (login limits in PR #73) | #14, #40 |
| TH-73 | DF4 P3 → DS1 | T | no | Queries altered or injected | SQL injection | String-built SQL | Only ORM and bound parameters, Semgrep rule, DB role without superuser | SR-03 | High | Part. (PR #69) | #12, #33 |
| TH-74 | DF4 P3 → DS1 | I | yes | Database traffic with PHI readable (plain connection) | Sniffing from a compromised pod | Pod in the namespace | NetworkPolicy only backend → 5432; TLS to PostgreSQL not used for the demo (accepted) | SR-08 | Medium | Accepted | #41, #39 |
| TH-75 | DF4 P3 → DS1 | D | no | Connection exhaustion or long locks | Many parallel bookings | Load | Pool and timeout settings, serialised conflicting writes, DB-level constraints | SR-03 | Medium | Part. (PR #69) | #74 |
| TH-76 | DF5 DS2 → P3 | T, I, D | yes | Secrets exposed or lost on their way into the pod | Secret printed in a log; environment dump; wrong format | Debug output, shell in pod | `secretKeyRef` into the backend only, log redaction, no shell in the distroless image, startup validation without printing values | SR-05, SR-04 | Medium | Part. (validation and redaction on `main`) | #30, #28 |
| TH-77 | DF6 DS2 → DS1 | T, I, D | yes | DB password exposed or wrong | Password visible in pod spec; mismatch with the backend URL | Operator error | One generated value shared by two Secrets, mounted only into the database pod, setup script creates a separate application user | SR-05 | Medium | Not impl. | #39, #30 |
| TH-78 | DF7 E4 → DS3 | T, I, D | yes | Malicious or secret-containing push; pushes block the repository | Code with a backdoor; `.env` in a commit | Compromised account | Pull request and review, push protection, Gitleaks, ruleset, review of workflow changes | SR-06, SR-05 | High | Part. | #31, #33 |
| TH-79 | DF8 DS3 → P4 | T, I, D | yes | Trigger or checkout manipulated | Fork PR with changed workflow; stale checkout | Unprotected triggers | Trigger only on `main` for build and sign, PR runs scans only, pinned `actions/checkout` | SR-06 | Medium | Not impl. | #31 |
| TH-80 | DF9 DS5 → P4 | T, I, D | yes | Secrets exposed or withheld | Key exfiltration by a step | Broad secret scope | Secrets scoped to the sign job, masked in logs, `GITHUB_TOKEN` per run | SR-05, SR-07 | High | Not impl. | #30, #35 |
| TH-81 | DF10 P4 → DS4 | T, I, D | yes | Image or signature replaced, or push token abused | Overwritten tag; stolen token | Token with broad scope | `packages: write` only on the push job, digest output, signature and SBOM attached to the digest | SR-07, SR-06 | High | Not impl. | #34, #35 |
| TH-82 | DF11 DS4 → P5 | T, I, D | yes | Unsigned or swapped image pulled | Registry or DNS tampering; wrong tag | No verification | Pull by digest, `cosign verify` before loading, fallback `.tar` with digest check | SR-07 | High | Not impl. | #35, #42 |
| TH-83 | DF12 P4 → P5 | T, I, D | yes | Manifests or digests tampered with in the deploy step | Deploy job applies a different image | Deploy job compromised | Quality gate before deploy, signature verification again in the deploy job, manifests only from the repository | SR-07, SR-06 | High | Not impl. | #36, #43 |
| TH-84 | DF13 P4 → DS3 | T, I, D | yes | Evidence forged or leaks data; commit loop | Fake report committed; secrets in a report | Write rights on `contents` | `contents: write` only on the evidence job, `paths-ignore` against loops, reports contain findings, never secrets | SR-06, SR-05 | Medium | Not impl. | #44, #31 |
| TH-85 | DF14 E5 → P5 | T, I, D | yes | Wrong or malicious cluster setup applied locally | Modified Makefile or manifest | Local repository changed | Repository review, `make up` idempotent and verifying, images by digest | SR-08, SR-07 | Medium | Not impl. | #42 |
| TH-86 | DF15 E5 → DS2 | T, I, D | yes | Generated secrets leak through the shell or files | Secret in shell history or a temp file | Local access | Generated at runtime with `openssl rand`, piped into `kubectl` without writing files, never overwritten if present | SR-05 | Medium | Not impl. | #30, #42 |
| TH-87 | DF16 P5 → P3 | T, I, D | yes | Probes abused or too verbose | Hammering `/readyz`; health endpoint reveals versions | Network reach | Status word only, no auth needed by design, NetworkPolicy limits callers, probes logged at DEBUG | SR-04 | Low | Implemented | #11 |
| TH-88 | DF17 P3 → P5 | T, I, D | yes | Logs forged, lost or leaking | Log injection; password in a log | Unfiltered user input in logs | JSON logs with redaction of sensitive fields, client request ID ignored, no bodies logged, path without query string | SR-04, SR-10 | Medium | Implemented | #11, #20 |

## 3. Coverage matrix

Every applicable pair of element and STRIDE category has at least one threat row. A dash means the category is not analysed for this element type (see the method table).

| Element | S | T | R | I | D | E |
| --- | --- | --- | --- | --- | --- | --- |
| E1 Patient | TH-01 | – | TH-02 | – | – | – |
| E2 Staff / Doctor | TH-03 | – | TH-04 | – | – | – |
| E3 Admin | TH-05 | – | TH-06 | – | – | – |
| E4 Developer | TH-07 | – | TH-08 | – | – | – |
| E5 Operator | TH-09 | – | TH-10 | – | – | – |
| P1 ingress-nginx | TH-11 | TH-12 | TH-13 | TH-14 | TH-15 | TH-16 |
| P2 Frontend | TH-17 | TH-18 | TH-19 | TH-20 | TH-21 | TH-22 |
| P3 Backend API | TH-23, TH-24 | TH-25, TH-26 | TH-27 | TH-28, TH-29 | TH-30, TH-31 | TH-32, TH-33, TH-34 |
| P4 Pipeline | TH-35 | TH-36 | TH-37 | TH-38 | TH-39 | TH-40 |
| P5 API server + kubelet | TH-41 | TH-42 | TH-43 | TH-44 | TH-45 | TH-46 |
| DS1 PostgreSQL | – | TH-47 | TH-48 | TH-49 | TH-50 | – |
| DS2 Kubernetes Secrets | – | TH-51 | TH-52 | TH-53 | TH-54 | – |
| DS3 Git repository | – | TH-55 | TH-56 | TH-57 | TH-58 | – |
| DS4 GHCR | – | TH-59 | TH-60 | TH-61 | TH-62 | – |
| DS5 GitHub secrets | – | TH-63 | TH-64 | TH-65 | TH-66 | – |
| DF1 | – | TH-67 | – | TH-67 | TH-68 | – |
| DF2 | – | TH-69 | – | n/a (public content) | TH-69 | – |
| DF3 | – | TH-70 | – | TH-71 | TH-72 | – |
| DF4 | – | TH-73 | – | TH-74 | TH-75 | – |
| DF5 | – | TH-76 | – | TH-76 | TH-76 | – |
| DF6 | – | TH-77 | – | TH-77 | TH-77 | – |
| DF7 | – | TH-78 | – | TH-78 | TH-78 | – |
| DF8 | – | TH-79 | – | TH-79 | TH-79 | – |
| DF9 | – | TH-80 | – | TH-80 | TH-80 | – |
| DF10 | – | TH-81 | – | TH-81 | TH-81 | – |
| DF11 | – | TH-82 | – | TH-82 | TH-82 | – |
| DF12 | – | TH-83 | – | TH-83 | TH-83 | – |
| DF13 | – | TH-84 | – | TH-84 | TH-84 | – |
| DF14 | – | TH-85 | – | TH-85 | TH-85 | – |
| DF15 | – | TH-86 | – | TH-86 | TH-86 | – |
| DF16 | – | TH-87 | – | TH-87 | TH-87 | – |
| DF17 | – | TH-88 | – | TH-88 | TH-88 | – |

## 4. Summary

88 threats. The tables below count them per STRIDE category (a row with several categories counts for each), per status and per risk. The counts were computed from the tables above with a script; update them when rows or statuses change.

| STRIDE category | Threats | Main mitigations and their state |
| --- | --- | --- |
| Spoofing | 11 | Authentication, MFA, rate limits, SHA-pinned actions: mostly planned, login and sessions in PR #73 |
| Tampering | 28 | Validation, constraints, signatures, digests, pipeline integrity: partly planned |
| Repudiation | 15 | Audit log (#20) and evidence (#44): planned |
| Information disclosure | 27 | Error handling, secrets, TLS, NetworkPolicy: partly on `main` |
| Denial of service | 28 | Rate limits, resource limits, constraints: partly planned |
| Elevation of privilege | 7 | RBAC, object-level checks, TBAC, security context: planned |

| Status | Threats |
| --- | --- |
| Implemented | 2 |
| Partially | 25 |
| Not implemented | 48 |
| Accepted | 13 |

| Risk (inherent) | Threats |
| --- | --- |
| High | 30 |
| Medium | 34 |
| Low | 24 |

**Selected categories** (decided in [#9](https://github.com/jankrus/doctorholiday/issues/9), see [stride-selection.md](stride-selection.md)): Spoofing, Elevation of privilege, Information disclosure. Tampering, Repudiation and Denial of service are justified there as not implemented as dedicated countermeasures.

| Selection | Threats | Implemented | Partially | Not implemented | Accepted |
| --- | --- | --- | --- | --- | --- |
| Selected (S, E, I) | 45 | 2 | 11 | 25 | 7 |
| Not selected (T, R, D only) | 43 | 0 | 14 | 23 | 6 |

A threat with several categories counts as selected if one of them is selected, so flows with T, I and D belong to the selected group through I.

## 5. Open points and assumptions

- **Plain traffic inside the cluster** (TH-71, TH-74) is accepted for a single-node local cluster and has to be named under brief §5e and in `deviations.md` if we keep it.
- **No etcd or volume encryption** (TH-49, TH-53) and **no Kubernetes audit log** (TH-10, TH-43, TH-52) are accepted for the kind demo.
- **Selection and status:** threats marked *no* are not driven by this analysis. Some of them are still reduced by controls that exist for other requirements (for example parameterised queries in SR-03 or image signing in SR-07); [stride-selection.md](stride-selection.md) lists them.
- **Branch ruleset enforcement** (TH-07, TH-08, TH-55, TH-56) depends on GitHub Pro for the private repository; until then four-eyes is a team rule.
- **Ratings** are the team's estimate for a local demo; a production system would add a quantitative score.
- The counts in the summary come from a one-off script that parses the tables; it is not part of the repository yet.
