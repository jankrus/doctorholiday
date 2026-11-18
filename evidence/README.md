# evidence

Reports of the pipeline runs, one tree per image (exam brief §7a-v):

```
evidence/<image>/{run,sast,sbom,sca,secrets,signing}/<run number>-<short sha>-<file>
```

- `run/`: logs of the finished jobs, the result of every job (`job-results.json`), digest and reference of the image by digest, build provenance.
- `sast/`, `sca/`, `secrets/`, `sbom/`: Semgrep, Trivy (lockfiles), Gitleaks and CycloneDX reports.
- `signing/`: cosign verification and attestation reports (from #35).

The `evidence` job of the pipeline writes to the **`evidence` branch**, not to `main`, because `main` is protected by a ruleset that requires a reviewed pull request (deviation D-09). Before the submission, `make evidence-sync` copies the branch into this directory for a normal pull request. `make evidence RUN_ID=<id>` rebuilds the evidence of a single run by hand.

Every run adds files with its own prefix; existing files are never overwritten.
