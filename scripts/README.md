# scripts

Helper scripts used by the Makefile and the pipeline (quality gate, packaging).

| Script | Purpose | Issue |
| :--- | :--- | :--- |
| [`check-pinning.sh`](check-pinning.sh) | Fails if a GitHub Action (workflow or local composite action) is not pinned by commit SHA (with a version comment) or a container image in a Dockerfile, a YAML file or a `*_IMAGE` variable of the Makefile and scripts is not pinned by digest (opt-out for locally built images: `# pinning-ignore: <reason>`). Run by `make check-pinning` and by the `meta` job of the pipeline. | #31 |

| [`scan.sh`](scan.sh) | `sbom`, `sast`, `sca` and `secrets` stages: SBOM (Syft), Semgrep, Trivy on the lockfiles, Gitleaks, as pinned container images. Reports in `reports/`. Run by the pipeline and on a laptop. | #32, #33 |
| [`report_stats.py`](report_stats.py) | Counts findings in the reports and validates them (fails on a missing, empty or malformed report). | #32, #33 |

| [`k8s-apply-pinned.sh`](k8s-apply-pinned.sh) | Downloads an upstream manifest (Calico, the Traefik CRDs), verifies its SHA-256 and only then applies it. | #40, #41 |
| [`k8s-secrets.sh`](k8s-secrets.sh) | Generates the cluster secrets at deploy time (database passwords, MFA key, session secret, TLS certificate); idempotent, never overwrites, never prints values. | #30, #39, #42 |
| [`test-netpol.sh`](test-netpol.sh) | Proves that the NetworkPolicies are enforced: three connections that must be blocked, three that must work. Run by `make verify`. | #41 |

Planned: `quality-gate.sh` (#36), `smoke-test.sh` (#43), packaging (#51).
