# scripts

Helper scripts used by the Makefile and the pipeline (quality gate, packaging).

| Script | Purpose | Issue |
| :--- | :--- | :--- |
| [`check-pinning.sh`](check-pinning.sh) | Fails if a GitHub Action (workflow or local composite action) is not pinned by commit SHA (with a version comment) or a container image in a Dockerfile, a YAML file or a `*_IMAGE` variable of the Makefile and scripts is not pinned by digest (opt-out for locally built images: `# pinning-ignore: <reason>`). Run by `make check-pinning` and by the `meta` job of the pipeline. | #31 |

| [`scan.sh`](scan.sh) | `sbom`, `sast`, `sca` and `secrets` stages: SBOM (Syft), Semgrep, Trivy on the lockfiles, Gitleaks, as pinned container images. Reports in `reports/`. Run by the pipeline and on a laptop. | #32, #33 |
| [`collect-evidence.sh`](collect-evidence.sh), [`fetch-run-logs.sh`](fetch-run-logs.sh), [`publish-evidence.sh`](publish-evidence.sh) | Evidence of a pipeline run: sort the artifacts into `evidence/<image>/<type>/<run>-<sha>-<file>`, save the job logs, push to the `evidence` branch. Used by the `evidence` job and `make evidence`. | #44 |
| [`build-image.sh`](build-image.sh) | Builds one image with a pinned BuildKit, pushes it with the tags `<VERSION>` and `<VERSION>-<shortsha>` and provenance, checks digest and labels in the registry, and writes `digest.txt` and `image-ref.txt`. Run by the `build` job. | #34 |
| [`quality_gate.py`](quality_gate.py), [`test_quality_gate.py`](test_quality_gate.py) | The quality gate: evaluates the Gitleaks, Trivy and Semgrep reports and runs `verify-image.sh`; exit code 1 on a secret, a HIGH/CRITICAL or CVSS >= 7.0 finding, a missing or invalid signature, a missing report or a job that did not succeed. Writes `reports/gate/quality-gate.json`. Run locally: `python3 scripts/quality_gate.py` on downloaded reports (`make test-gate` runs the tests). `scan.sh image <c>` makes the Trivy image report it reads. See [quality-gate.md](../docs/architecture/quality-gate.md). | #36 |
| [`report_stats.py`](report_stats.py) | Counts findings in the reports and validates them (fails on a missing, empty or malformed report); reads the digest of a build and checks image labels. | #32, #33, #34 |

| [`k8s-apply-pinned.sh`](k8s-apply-pinned.sh) | Downloads an upstream manifest (Calico, the Traefik CRDs), verifies its SHA-256 and only then applies it. | #40, #41 |
| [`k8s-secrets.sh`](k8s-secrets.sh) | Generates the cluster secrets at deploy time (database passwords, MFA key, session secret, TLS certificate); idempotent, never overwrites, never prints values. | #30, #39, #42 |
| [`test-netpol.sh`](test-netpol.sh) | Proves that the NetworkPolicies are enforced: three connections that must be blocked, three that must work. Run by `make verify`. | #41 |

| [`smoke-test.sh`](smoke-test.sh) | Smoke test of the running app through the ingress: frontend, refused anonymous API call, CSRF check, register and login of two accounts (the first one must be `ADMIN` on a fresh cluster), patient reads, logout. Run by the `deploy` job and `make smoke`. | #43 |
| [`check_pod_security.py`](check_pod_security.py) | Checks the running pods (`kubectl get pods -o json`): not privileged, no privilege escalation, read-only root file system, non-root, capabilities dropped, seccomp, no host namespaces, no mounted token. | #43 |
| [`k8s-registry-overlay.sh`](k8s-registry-overlay.sh), [`k8s-pull-secret.sh`](k8s-pull-secret.sh) | `IMAGE_SOURCE=registry`: write a Kustomize overlay that replaces the application images by the digests of `image-ref.txt` (only `ghcr.io/jankrus/doctorholiday-*` by digest are accepted), and create the GHCR pull secret from `GHCR_USER` / `GHCR_TOKEN`. | #43 |
| [`gate-demo.sh`](gate-demo.sh) | Gate demonstration (workflow `gate-demo.yml`): `prepare` puts one fault into the checkout (`secret`, `vulnerability`, `unsigned`; `clean` is the control), `assert` checks that the gate blocked for exactly that reason. Nothing is committed or pushed. | #36 |

Planned: packaging (#51).
