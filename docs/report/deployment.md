# Deployment from the pipeline

Brief §3, issue #43. After the quality gate, the pipeline deploys the **signed images, by digest**, to a Kubernetes cluster and tests the result. The registry (GHCR) is the intermediate instance between build and cluster.

## Approach: ephemeral kind cluster on the runner (option A)

| | A: kind on the GitHub-hosted runner (chosen) | B: self-hosted runner on a team laptop |
| :--- | :--- | :--- |
| Isolation | a fresh VM per run, destroyed afterwards | the laptop; a run can leave state behind |
| Security | no runner of ours that stays reachable | a self-hosted runner executes workflow code; on a public repository a fork pull request can run code on the laptop; acceptable only for a private repository with restrictions |
| Reproducibility | every run starts from nothing, the same Makefile targets as `make up` | depends on the state of the machine |
| "Local cluster" | the same kind cluster as the one of `make up`, created on the runner | closer to "local", but what ran on the laptop is harder to prove |
| Cost | GitHub-hosted minutes (free for a public repository) | none, but a machine that must be on |

Decision: **A**. What the deployment has to show is that the pipeline deploys exactly the signed digest and that the app works. That is shown the same way on a throw-away cluster, and no machine of ours has to run code of the repository.

## What the `deploy` job does

1. Downloads `image-backend` and `image-frontend` (digest and `image-ref.txt` of the build job) into `reports/images/`.
2. Installs cosign and kind (version and SHA-256 pinned in `infrastructure/kind/versions.env`).
3. `make up IMAGE_SOURCE=registry`, the same targets as on a laptop: cluster, Calico, Traefik, secrets, then **`registry-images`**: `scripts/verify-image.sh` for both images (signature and SBOM attestation with `infrastructure/signing/cosign.pub`; the job stops here if one fails) and the overlay with the digests. The cluster pulls the images itself; with `GHCR_USER` / `GHCR_TOKEN` it gets a pull secret, so private packages work too. Then the manifests, the migration and the wait for Ready.
4. `scripts/smoke-test.sh` (the first login on the fresh cluster must make the first account `ADMIN`).
5. `make verify`: the NetworkPolicy test (`scripts/test-netpol.sh`).
6. `scripts/check_pod_security.py` on `kubectl get pods -o json`: not privileged, no privilege escalation, read-only root file system, non-root, capabilities dropped, seccomp `RuntimeDefault`, no host namespaces, no mounted service account token. The pods' `imageID` shows which digest runs.
7. Uploads the artifact `deploy` (smoke test, NetworkPolicy report, pod JSON and security check); the `evidence` job sorts it into `evidence/<image>/run/`. The deployed digests are also in the job summary.

The job `needs` the quality gate and has no `always()`: a run whose gate fails never reaches it.

## Run it on a laptop

```sh
# digests of a pipeline run: gh run download <id> --name image-backend --dir reports/images/backend (and frontend)
make up IMAGE_SOURCE=registry     # needs cosign; GHCR_USER / GHCR_TOKEN only for private packages
make smoke
make verify
```

Checked by hand for #43 against a local kind cluster with the images of runs 65 and 68 from GHCR: both signatures verified, the pods run exactly the digests of the evidence, the smoke test and the pod security check pass.

## Not done

See deviation D-11 in [deviations.md](deviations.md): the smoke test does not set working hours or book (no doctor accounts exist before #55 and #18), and the digests are not committed back to the manifests.

## Demonstration (acceptance of #43)

| Criterion | Run |
| :--- | :--- |
| green run on `main` with deploy, smoke test and digest | not run yet |
| a run whose gate fails never reaches deploy | not run yet (the gate demonstration of #36) |
