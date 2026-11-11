# .github/workflows

CI/CD pipeline of Doctor Holiday: [`ci-cd.yml`](ci-cd.yml). The skeleton is issue [#31](https://github.com/jankrus/doctorholiday/issues/31); the stages are filled in by #32 to #36, #43 and #44. Requirements it serves: SR-06 (SBOM, scans, blocking gate) and SR-07 (signed images) in [security-requirements.md](../../docs/architecture/security-requirements.md).

## Triggers

| Event | What runs |
| :--- | :--- |
| `push` to `main` (not for changes only under `docs/` or `evidence/`) | the whole pipeline |
| `pull_request` to `main` (same path filter) | `meta`, both test jobs, `sbom` and the three scans, never build, sign, deploy or evidence |
| `workflow_dispatch` | the whole pipeline, started by hand |

`evidence/**` is ignored so the evidence commit of #44 cannot trigger a new run. A pull request can never sign, write to the registry or deploy.

## Job graph

```
meta ─┬─ test-backend ──┐
      ├─ test-frontend ─┤
      └─ sbom ─┬─ sast ─┤
               ├─ sca ──┼─ build (frontend, backend) ─ sign ─ quality-gate ─ deploy ─ evidence
               └─ secrets ┘
```

| Job | Brief step | State | Issue |
| :--- | :--- | :--- | :--- |
| `meta` | – | **real:** pinning check, reads `VERSION.txt` (SemVer check) and exposes `version`, `short_sha`, `tag_version`, `tag_sha` | #31 |
| `test-backend` | – | **real:** `make -C backend lint`, `make test-db` (throwaway PostgreSQL, real migrations) | #31 |
| `test-frontend` | – | **real:** `npm ci --ignore-scripts`, lint, tests, build | #31 |
| `sbom` | (a) | **real:** CycloneDX SBOM of `frontend/` and `backend/` (Syft), validated with the CycloneDX CLI, artifact `sbom`. SBOM per built image follows with #34/#35 | #32 |
| `sast` | (b) | **real:** Semgrep (registry packs + `.semgrep/`), JSON and SARIF per component, artifact `sast`; SARIF to code scanning if `CODE_SCANNING=true` | #33 |
| `sca` | (b) | **real:** Trivy on the lockfiles (`package-lock.json`, `uv.lock`), full report, the gate counts HIGH and CRITICAL, artifact `sca`. `trivy image` follows with #34 | #33 |
| `secrets` | (b) | **real:** Gitleaks over the full history with `.gitleaks.toml`, values redacted, artifact `secrets` | #33 |
| `build` | (c) | stub, matrix `frontend` / `backend` | #34 |
| `sign` | (d) | stub, matrix `frontend` / `backend` | #35 |
| `quality-gate` | (e) | stub | #36 |
| `deploy` | deployment | stub | #43 |
| `evidence` | §7 evidence | stub, runs even after a failure | #44 |

A failed job stops everything behind it through `needs:`. Only `evidence` uses `if: always()`, because a blocked run is evidence too.

## Rules for every change

1. **Pin actions by full commit SHA** with the version as a comment: `uses: owner/repo@<40 hex> # v1.2.3`. Never a tag or a branch.
2. **Pin container images by digest**, in Dockerfiles, `compose.yaml` and tool invocations.
3. **Least privilege:** `permissions: {}` at the top; each job lists only what it uses, with a comment saying why. Write permissions exist only on `build` and `sign` (`packages: write`) and on `evidence` (`contents: write`).
4. **No untrusted input in `run:`.** Branch names, PR titles and similar go through `env:`.
5. **No secrets in the workflow file.** Secrets come from GitHub encrypted secrets and only reach the job that needs them (#30, #35).
6. **No cache of third-party artefacts** in the signing path (`enable-cache: false`); cache poisoning would end up in a signed image.

## Scans and reports

`scripts/scan.sh sbom|sast|sca|secrets` is the only place that knows the tools. The jobs call it, so a report can be reproduced on a laptop with Docker (`scripts/scan.sh sast` and so on). All tools run as images pinned by digest. Reports land in `reports/<kind>/` (git-ignored) and are uploaded as artifacts (90 days); the evidence job (#44) copies them to `evidence/<image>/`.

| Kind | Tool | Files in `reports/` | Job output |
| :--- | :--- | :--- | :--- |
| `sbom` | Syft 1.57.1, CycloneDX CLI 0.33.1 | `sbom/sbom-<component>-<version>-<shortsha>.cdx.json` | `components` |
| `sast` | Semgrep 1.185.0 | `sast/semgrep-<component>.json`, `.sarif` | `findings` |
| `sca` | Trivy 0.76.2 | `sca/trivy-fs-<component>.json`, `.sarif` | `findings` (HIGH + CRITICAL) |
| `secrets` | Gitleaks 8.30.1 | `secrets/gitleaks.json`, `.sarif` | `findings` |

- The scans **report and succeed**: they exit 0 on findings so the reports are always uploaded. Until the quality gate (#36) exists, findings do not fail a run.
- `scripts/report_stats.py` counts findings and fails on a missing, empty or malformed report, so a scan that produced nothing never looks clean.
- Ignored findings are listed with a justification in [deviations.md](../../docs/report/deviations.md#scanner-exceptions-33).
- A fake secret on a throwaway branch is reported by Gitleaks as `github-pat` with the value redacted (demonstrated in the pull request of #33). A push of such a branch to GitHub is blocked by secret push protection, so the demonstration for the gate (#36) needs a test pattern that push protection accepts.

## Check locally

```sh
make check-pinning   # actions by SHA with version comment, images by digest (scripts/check-pinning.sh)
make lint-actions    # check-pinning + actionlint + zizmor (needs Docker; tool images are pinned by digest)
```

`meta` runs `scripts/check-pinning.sh` in every pipeline run, so a mutable reference fails the first job. zizmor runs offline locally; its online audits (impostor commits, known-vulnerable actions) need a GitHub token and belong into the pipeline (#33).

## Pinned actions

| Action | Version | Commit |
| :--- | :--- | :--- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-node` | v7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| `actions/setup-python` | v7.1.0 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| `astral-sh/setup-uv` | v10.3.3 | `68559e99cc807c1eb7e9238fd43a15bba460eec2` |
| `actions/upload-artifact` | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |
| `github/codeql-action/upload-sarif` | v4.39.3 | `33d7b85da1a04171e211befe2c739303b9a4c066` |

Updates come as Dependabot pull requests (#46), which keep the SHA and the comment together.

## Open points

- **Evidence commit:** committing reports to `main` is blocked by the branch ruleset (pull request required). #44 decides between an evidence branch and a bot token.
- **First real run:** the acceptance criterion "a push to `main` runs all jobs in order" can only be checked after this pull request is merged.
- **Image scans:** SBOM per image digest and `trivy image` (also its secret scanner) wait for the images of #34.
- **Required status checks** for the ruleset (`protect-main`) are added once the first run is green: `meta`, `test (backend)`, `test (frontend)`.
  Caveat: because of `paths-ignore`, a pull request that only changes `docs/` or `evidence/` starts no run, and GitHub would wait forever for a required check. Before the checks become required, either drop `paths-ignore` for `pull_request` or add a small always-running job that reports the same check names.
