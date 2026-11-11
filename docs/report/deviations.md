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

## D-03: `python:3.12-alpine` instead of distroless or Chainguard for the backend image

- **Decided in:** [#28](https://github.com/jankrus/doctorholiday/issues/28), deviating from [ADR-001 §3.2](../architecture/adr/ADR-001-tech-stack.md), which names `cgr.dev/chainguard/python` or `gcr.io/distroless/python3`.
- **Why:** The backend needs Python 3.12 (`requires-python = ">=3.12,<3.13"`, [ADR-002](../architecture/adr/ADR-002-python-package-manager.md)). The Distroless Python images ship 3.11 (Debian 12) or 3.13 (Debian 13), not 3.12. Chainguard publishes version tags such as `3.12` only for paying customers; its free `latest` tag moves to a newer Python and cannot be reproduced. `python:3.12-alpine`, pinned by digest, is the smallest official image with the right interpreter.
- **Consequence:** The image still has a shell (`/bin/sh`) and `apk`. To reduce the surface the runtime stage removes `pip`, `setuptools` and `wheel`, runs as a numeric non-root user, needs no capabilities and works with a read-only root filesystem. The build installs only hash-locked wheels (`uv sync --locked --no-build`). Trivy reports no HIGH or CRITICAL finding.
- **Production alternative:** a distroless image with a matching Python version, or a Chainguard subscription.

## D-04: `apk upgrade` at image build and mainline nginx for the frontend image

- **Decided in:** [#28](https://github.com/jankrus/doctorholiday/issues/28).
- **Why:** The pinned base images are a few weeks old when they are built. Trivy then reports HIGH and CRITICAL findings in Alpine libraries (for example `krb5-libs`, `libexpat`, `libcurl`, `musl`) whose fixes Alpine has already published. The quality gate (brief §3e) would block every build. Both runtime stages therefore run `apk upgrade --no-cache`. The frontend uses the mainline `nginxinc/nginx-unprivileged:alpine` (ADR-001), because the 1.28 stable line carries nginx findings without a fix in its package repository.
- **Consequence:** An image is no longer a pure function of the base digest and the sources: it also depends on the Alpine package index at build time. Reproducibility is restored by the digest of the *built* image (pushed and signed in #34, #35) and by the SBOM, which lists the exact package versions (#32). Two builds on different days can differ in patch versions.
- **Production alternative:** rebuild images on a schedule and bump the base digest through Dependabot (#46) instead of upgrading inside the build.

## Planned or likely deviations (not decided yet)

| ID | Topic | Note |
| :--- | :--- | :--- |
| D-05 | Signature verification at cluster admission (#45) | Stretch goal. If skipped, signatures are verified only in the pipeline quality gate; the brief asks for exactly that. |
| D-06 | Self-signed TLS certificate on the kind ingress (#40) | No public CA for a local cluster. Clients must trust the certificate manually. |
| D-07 | First-admin bootstrap without a setup token | Brief §4 demands that the first login becomes admin. Residual risk is documented in roles-and-permissions.md. |
