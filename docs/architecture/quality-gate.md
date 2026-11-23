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

The three failure modes are demonstrated with `workflow_dispatch` runs; links are added here once they exist:

| Failure mode | Run |
| :--- | :--- |
| a dummy secret in the history | not run yet |
| a known-vulnerable dependency | not run yet |
| an unsigned image reference | not run yet |

A gate run is only possible on `main` (release run, [workflow README](../../.github/workflows/README.md)), so a demonstration needs a short-lived change on `main` that is reverted afterwards, or the local run of the script on fixture reports (`make test-gate`) as the reproducible proof.
