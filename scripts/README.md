# scripts

Helper scripts used by the Makefile and the pipeline (quality gate, packaging).

| Script | Purpose | Issue |
| :--- | :--- | :--- |
| [`check-pinning.sh`](check-pinning.sh) | Fails if a GitHub Action (workflow or local composite action) is not pinned by commit SHA (with a version comment) or a container image in a Dockerfile, a YAML file or a `*_IMAGE` variable of the Makefile and scripts is not pinned by digest (opt-out for locally built images: `# pinning-ignore: <reason>`). Run by `make check-pinning` and by the `meta` job of the pipeline. | #31 |

| [`scan.sh`](scan.sh) | `sbom`, `sast`, `sca` and `secrets` stages: SBOM (Syft), Semgrep, Trivy on the lockfiles, Gitleaks, as pinned container images. Reports in `reports/`. Run by the pipeline and on a laptop. | #32, #33 |
| [`build-image.sh`](build-image.sh) | Builds one image with a pinned BuildKit, pushes it with the tags `<VERSION>` and `<VERSION>-<shortsha>` and provenance, checks digest and labels in the registry, and writes `digest.txt` and `image-ref.txt`. Run by the `build` job. | #34 |
| [`report_stats.py`](report_stats.py) | Counts findings in the reports and validates them (fails on a missing, empty or malformed report); reads the digest of a build and checks image labels. | #32, #33, #34 |

Planned: `quality-gate.sh` (#36), `smoke-test.sh` and `test-netpol.sh` (#43), packaging (#51).
