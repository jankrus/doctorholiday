# Deviations from the exam brief and from our own decisions

The brief allows deviations "sofern sie schlüssig begründet und reflektiert werden". This file lists every deviation, why it was made and what we accept as a consequence. Add an entry in the same PR that introduces a deviation (AGENTS.md, rule 9).

Brief §5e ("Erklärung aller nicht-sicheren Parts mit Begründung") draws on this file and on the residual risks named in [roles-and-permissions.md](../architecture/roles-and-permissions.md).

## D-01: Vite 8 and Vitest 5 instead of Vite 5 and Vitest 3

- **Decided in:** [ADR-004 §3.1](../architecture/adr/ADR-004-frontend-libraries.md), deviating from [ADR-001 §3.1](../architecture/adr/ADR-001-tech-stack.md).
- **Why:** `npm audit` reports HIGH (Vite) and CRITICAL (Vitest/tinypool) advisories against the latest Vite 5 and Vitest 3 that are fixed only in newer majors. A project whose quality gate blocks on CVSS ≥ 7.0 should not start on vulnerable tooling.
- **Consequence:** Node.js ≥ 22.13 is required. React stays at 18 and ESLint at 8 as decided in ADR-001. Both tools are build and test tooling only and never reach the nginx image.
- **Follow-up:** ADR-001 §3.1 still names Vite 5. Mark it as superseded by ADR-004.

## D-02: `argon2-cffi` directly instead of `passlib`

- **Decided in:** PR [#73](https://github.com/jankrus/doctorholiday/pull/73) (not merged yet), deviating from ADR-001 §3.1 and AGENTS.md.
- **Why:** `passlib` is unmaintained (last release 2020) and imports the deprecated `crypt` module. Argon2id stays the hashing algorithm; only the wrapper library is dropped (fewer dependencies, smaller SCA surface).
- **Consequence:** none for the security properties. ADR-001 and AGENTS.md must be updated when #73 merges.

## Scanner exceptions (#33)

Findings are never hidden silently. Every ignore entry lives in one of the files below, with a justification, and is listed here. Anything not listed is scanned and counted.

| Scanner | Ignored | Where | Justification |
| :--- | :--- | :--- | :--- |
| Semgrep | `**/*.test.ts`, `**/*.test.tsx`, `backend/tests/` | `.semgrepignore` | Tests contain fixed dummy values (TOTP secrets, one-time codes, passwords) that the generic-secret rule (`detected-generic-secret`) flags, 4 findings in `MfaPage.test.tsx`, and test-only constructs that the Python packs flag (5 warnings: `hardcoded-password-default-argument`, `len-all-count`, `dynamic-urllib-use-detected`). None is a real credential or runs in production, and test files are not part of any image. |
| Semgrep | `frontend/dev-mock-api.ts` | `.semgrepignore` | Mock of the API that only the Vite dev server loads (`vite.config.ts`), never built into the image. Its demo TOTP secret is a fixed dummy value (`detected-generic-secret`). |
| Semgrep | rule `python.lang.compatibility.python37.python37-compatibility-importlib2` | `scripts/scan.sh` (`--exclude-rule`) | Flags `importlib.resources` as unavailable before Python 3.7. The backend runs on Python 3.12 only (`requires-python`). |
| Trivy | none | `.trivyignore` (empty) | No vulnerability is ignored. |
| Gitleaks | none | `.gitleaks.toml` (default rules, no allowlist) | No leak is ignored. |

## Planned or likely deviations (not decided yet)

| ID | Topic | Note |
| :--- | :--- | :--- |
| D-03 | Signature verification at cluster admission (#45) | Stretch goal. If skipped, signatures are verified only in the pipeline quality gate; the brief asks for exactly that. |
| D-04 | Self-signed TLS certificate on the kind ingress (#40) | No public CA for a local cluster. Clients must trust the certificate manually. |
| D-05 | First-admin bootstrap without a setup token | Brief §4 demands that the first login becomes admin. Residual risk is documented in roles-and-permissions.md. |
