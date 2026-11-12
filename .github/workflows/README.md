# .github/workflows

CI/CD pipeline of Doctor Holiday: [`ci-cd.yml`](ci-cd.yml). The skeleton is issue [#31](https://github.com/jankrus/doctorholiday/issues/31); the stages are filled in by #32 to #36, #43 and #44. Requirements it serves: SR-06 (SBOM, scans, blocking gate) and SR-07 (signed images) in [security-requirements.md](../../docs/architecture/security-requirements.md).

## Triggers

| Event | What runs |
| :--- | :--- |
| `push` to `main` (except commits that only change `evidence/`) | the whole pipeline (a *release run*) |
| `pull_request` to `main` | `meta`, both test jobs, `sbom` and the three scans, never build, sign, deploy or evidence |
| `workflow_dispatch` on `main` | the whole pipeline (a release run), started by hand |
| `workflow_dispatch` on any other branch | like a pull request: tests and scans only |

**Release run:** the `context` job sets `release=true` only for a push or manual run on `refs/heads/main`. Build, sign, quality gate, deploy and evidence ask `needs.context.outputs.release == 'true'`, one expression in one place. A pull request or a manual run on a feature branch can therefore never build and push an image, sign, deploy or write evidence.

**Every change to `main` triggers a run** (brief §3), also documentation. Only `evidence/**` is ignored, so the evidence commit of #44 cannot start a new run. (The issue text suggested ignoring `docs/**` as well; that would contradict "every change" and would leave documentation-only pull requests without the checks that later become required, so it is not done.)

**Concurrency:** the group is the commit (`github.sha`), so every push to `main` runs and gets its own evidence; a per-branch group would keep one running and one waiting run and cancel the older waiting one. Pull requests use the branch as group and cancel older runs. Only the `deploy` job holds a lock (`group: deploy`), because two deployments must not run at once; a deploy that is still waiting is replaced by a newer one.

## Job graph

```
context (release run?)
meta ─┬─ test-backend ──┐
      ├─ test-frontend ─┤
      └─ sbom ─┬─ sast ─┤
               ├─ sca ──┼─ build (frontend, backend) ─ sign ─ quality-gate ─ deploy ─ evidence
               └─ secrets ┘
```

| Job | Brief step | State | Issue |
| :--- | :--- | :--- | :--- |
| `context` | – | **real:** decides once whether this is a release run (`release` output); no checkout, no permissions | #31 |
| `meta` | – | **real:** pinning check, reads `VERSION.txt` (SemVer check) and exposes `version`, `short_sha`, `tag_version`, `tag_sha` | #31 |
| `test-backend` | – | **real:** `make -C backend lint`, `make test-db` (throwaway PostgreSQL, real migrations) | #31 |
| `test-frontend` | – | **real:** `npm ci --ignore-scripts`, lint, tests, build | #31 |
| `sbom` | (a) | stub | #32 |
| `sast`, `sca`, `secrets` | (b) | stubs | #33 |
| `build` | (c) | stub, matrix `frontend` / `backend` | #34 |
| `sign` | (d) | stub, matrix `frontend` / `backend` | #35 |
| `quality-gate` | (e) | stub | #36 |
| `deploy` | deployment | stub | #43 |
| `evidence` | §7 evidence | stub, runs even after a failure | #44 |

A failed job stops everything behind it through `needs:`. Only `evidence` uses `if: !cancelled() && release`: it runs after a failure of any job, also of `meta` (a failed pinning check is a blocked run, and a blocked run is evidence too), but not after a run was cancelled by hand, because it holds `contents: write`.

## Rules for every change

1. **Pin actions by full commit SHA** with the version as a comment: `uses: owner/repo@<40 hex> # v1.2.3`. Never a tag or a branch.
2. **Pin container images by digest**, in Dockerfiles, `compose.yaml` and tool invocations.
3. **Least privilege:** `permissions: {}` at the top; each job lists only what it uses, with a comment saying why. Write permissions exist only on `build` and `sign` (`packages: write`) and on `evidence` (`contents: write`).
4. **No untrusted input in `run:`.** Branch names, PR titles and similar go through `env:`.
5. **No secrets in the workflow file.** Secrets come from GitHub encrypted secrets and only reach the job that needs them (#30, #35).
6. **No cache of third-party artefacts** in the signing path (`enable-cache: false`); cache poisoning would end up in a signed image.

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

Updates come as Dependabot pull requests (#46), which keep the SHA and the comment together.

## Open points

- **Evidence commit:** committing reports to `main` is blocked by the branch ruleset (pull request required). #44 decides between an evidence branch and a bot token.
- **First real run:** the acceptance criterion "a push to `main` runs all jobs in order" can only be checked after this pull request is merged.
- **Required status checks** for the ruleset (`protect-main`) are added once the first run is green: `meta`, `test (backend)`, `test (frontend)`. Because no path filter applies to pull requests, every pull request starts them.
- **Pinning check gaps:** `scripts/check-pinning.sh` covers actions, Dockerfiles (`Dockerfile`, `Dockerfile.*`, `*.Dockerfile`, `Containerfile`), every `image:` key in YAML files (compose, Kubernetes manifests, kind configuration, workflow containers) and image variables (`*_IMAGE`) in the Makefile and shell scripts. It does **not** see an image that is only named inside a command line (`docker run <image>`), and not Kustomize `images:` entries (#38). "Passed" therefore means: everything the script can see is pinned, not everything.
