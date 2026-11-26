# Quality gate

Brief §3e, requirements SR-06 and SR-07, issue #36. Nothing is deployed unless the gate passes: the `deploy` job needs `quality-gate`, so a failed gate skips it.

## Rules

`scripts/quality_gate.py` checks all rules (it does not stop at the first violation, so the report is complete) and exits with 1 if one is violated.

| Rule | Violated when | Source |
| :--- | :--- | :--- |
| `secrets` | Gitleaks reports at least one finding in the full history | `reports/secrets/gitleaks.json` |
| `vulnerabilities` | a Trivy finding has severity HIGH or CRITICAL **or** a CVSS score >= 7.0 (highest score of any source, v3 before v2), in the lockfiles or in a pushed image; or a Semgrep finding has severity `ERROR` | `reports/sca/trivy-fs-*.json`, `reports/gate/trivy-image-*.json`, `reports/sast/semgrep-*.json` |
| `signatures` | for an image, `scripts/verify-image.sh` fails (no signature, wrong key, no SBOM attestation) or there is no reference by digest | `reports/images/<image>/image-ref.txt`, [signing.md](signing.md) |
| `jobs` | one of `sast`, `sca`, `secrets`, `build`, `sign` did not end with `success` | `toJSON(needs)` of the workflow |

**Fail closed.** A report that is missing, empty or not valid JSON is a violation, never a pass. A scan that produced nothing must not look like a clean scan.

**Semgrep has no CVSS score.** Its severity `ERROR` is treated as HIGH or CRITICAL; `WARNING` and `INFO` findings are listed in the SAST report but do not block. (The same mapping is used by `scripts/scan.sh sast`.)

**Exceptions.** A finding can only be accepted through `.trivyignore` (one justified entry, plus an entry in [deviations.md](../report/deviations.md)); the gate itself has no switch to skip a rule.

## Output

- `reports/gate/quality-gate.json`: every rule with its violations (finding id, package, version, severity, CVSS, file and line; Gitleaks values are redacted).
- A Markdown table on stdout, which the workflow appends to the job summary.
- The `gate` artifact (JSON report and the Trivy image reports) goes into `evidence/<image>/run/` through the `evidence` job (#44).

## Run it by hand

On downloaded reports (`gh run download <id>`; layout `reports/<kind>/`):

```sh
scripts/scan.sh image backend      # needs reports/images/backend/image-ref.txt, TRIVY_USERNAME/PASSWORD for a private image
python3 scripts/quality_gate.py    # exit code 1 = blocked
make test-gate                     # unit tests: each failure mode and the clean case
```

## Demonstration runs (acceptance of #36)

The gate is shown to block, for each rule, with the workflow [`gate-demo.yml`](../../.github/workflows/gate-demo.yml) (`gh workflow run gate-demo.yml -f scenario=<name>`). A release run only exists on `main` and `main` must not receive faulty commits, so the demo does not use the release pipeline: it puts **one fault into a throw-away checkout of the run** (`scripts/gate-demo.sh`), runs the **real scans and the real gate** (`scripts/quality_gate.py`, the same Semgrep, Trivy, Gitleaks and cosign checks as the release run) and then checks that the gate blocked for exactly that reason. Nothing is built, signed, pushed or deployed, and the fault is never committed. The run is red on purpose; its reports go to the `evidence` branch under the prefix `demo-<scenario>-<run number>`.

| Scenario | Fault | Rule that must block | Run |
| :--- | :--- | :--- | :--- |
| `clean` (control) | none | none, the gate passes | [passed](https://github.com/jankrus/doctorholiday/actions/runs/45626597215) |
| `secret` | a random token in the shape of a GitHub token, in a local commit | `secrets` | [blocked by `secrets`](https://github.com/jankrus/doctorholiday/actions/runs/45626604342) |
| `vulnerability` | `backend/requirements.txt` pins PyYAML 5.3 (CVE-2020-14343, CRITICAL) | `vulnerabilities` | [blocked by `vulnerabilities`](https://github.com/jankrus/doctorholiday/actions/runs/45626611223) |
| `unsigned` | the backend reference points to a public image that our key never signed | `signatures` | [blocked by `signatures`](https://github.com/jankrus/doctorholiday/actions/runs/45626616466) |

The image digests are those of the latest release run (read from the `evidence` branch). The `deploy` job is not part of the demo; that it is skipped when the gate fails follows from `needs: quality-gate` in `ci-cd.yml` and is shown by any red gate run of the release pipeline.

All four runs ended as expected on 2026-11-25 (the three fault runs are red on purpose; the step "Check that the gate decided as expected" is green in each). Their reports and job logs are on the `evidence` branch as `evidence/<image>/run/demo-<scenario>-<number>-*`. The gate also blocked a real run of the release pipeline: [run 87](https://github.com/jankrus/doctorholiday/actions/runs/45212878779) (Gitleaks false positives on the evidence branch, `deploy` skipped).

Found by the demonstration: the evidence branch is part of the history that Gitleaks scans, and the Trivy image reports contain the public Python signing key id of the base image; see the scanner exceptions in [deviations.md](../report/deviations.md).
