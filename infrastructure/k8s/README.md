# infrastructure/k8s

Kubernetes manifests of Doctor Holiday for namespace `doctorholiday` and the `make up` blueprint (issues #37 to #42, brief §4 and §7). The cluster is a local [kind](https://kind.sigs.k8s.io/) cluster; the manifests are plain YAML combined with Kustomize.

## Quick start

Prerequisites: Docker (daemon running), [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) `v0.33.0`, `kubectl` (at most one minor version away from the node's Kubernetes 1.35), `make`, `openssl`, `curl`, bash. Ports 80 and 443 on this machine must be free. On Windows use WSL2 (Ubuntu) with Docker Desktop's WSL integration.

```sh
make up        # cluster, CNI, ingress, namespace, secrets, images, manifests, wait, then prints "Ready"
```

Then open <https://doctorholiday.localhost> (self-signed certificate: accept the browser warning, or `curl -k`). **Register and log in right away: the first login becomes the admin** ([roles-and-permissions.md](../../docs/architecture/roles-and-permissions.md#bootstrapping-the-first-admin)).

| Target | What it does |
| :--- | :--- |
| `make up` | everything below, in this order, idempotent; ends with `Ready` |
| `make check-tools` | checks that the tools are installed and Docker runs |
| `make cluster` | creates the kind cluster from `infrastructure/kind/kind-config.yaml` if it does not exist |
| `make cni` | installs Calico (enforces NetworkPolicies) from a pinned, checksum-verified manifest |
| `make ingress` | installs the ingress controller Traefik (CRDs verified by checksum, Deployment pinned by digest in `infrastructure/kind/traefik.yaml`) and waits for it |
| `make namespace` | creates the namespace with Pod Security `restricted` |
| `make secrets` | generates the secrets (database passwords, MFA key, session secret, TLS certificate); never overwrites existing ones |
| `make db-config` | ConfigMaps for the database init script and the migrations, made from the files in the repository |
| `make images` | builds both images and loads them into the cluster |
| `make deploy` | applies `infrastructure/k8s` with Kustomize and runs the database migrations |
| `make wait` | waits until database, backend and frontend are Ready and the app answers |
| `make verify` | proves that the NetworkPolicies are enforced (`scripts/test-netpol.sh`) |
| `make status`, `make logs` | state and recent logs of the application |
| `make down` | deletes the cluster and everything in it |

All `kubectl` calls use the context `kind-doctorholiday`, so another cluster on the same machine is never touched. Running `make up` twice changes nothing the second time.

## What is in this directory

| File | Content | Issue |
| :--- | :--- | :--- |
| `namespace.yaml` | namespace with Pod Security Admission `restricted` (enforce, audit, warn) | #37 |
| `serviceaccounts.yaml` | one ServiceAccount per workload, no token, no Role anywhere | #37 |
| `configmap.yaml` | non-secret backend configuration | #38 |
| `backend.yaml`, `frontend.yaml` | Deployments and Services (ClusterIP 8080) | #38 |
| `postgres.yaml` | StatefulSet with a persistent volume and its Service (ClusterIP 5432) | #39 |
| `db-migrate.yaml` | Job that applies the migrations as the schema owner | #39 |
| `networkpolicies.yaml` | default deny plus the allowed flows | #41 |
| `ingress.yaml` | host `doctorholiday.localhost`, TLS, `/api` to the backend, `/` to the frontend | #40 |
| `kustomization.yaml` | entry point; sets the namespace and the image tags | #37 |

Not in this directory, on purpose: the Secrets (`db-credentials`, `backend-secrets`, `doctorholiday-tls`; created by `make secrets`, never committed) and the three ConfigMaps for the database (`postgres-init`, `db-migrate-script`, `db-migrations`), which `make db-config` builds from `infrastructure/postgres/` and `backend/migrations/` so those files stay the only copy.

## How the brief's requirements are met

| Brief §4 | Where |
| :--- | :--- |
| a: own namespace | `namespace.yaml`, everything lives in `doctorholiday` |
| b: minimal service account | `serviceaccounts.yaml`: four accounts, `automountServiceAccountToken: false` also in every pod, no Role or binding |
| c: `runAsNonRoot: true` | pod level in every workload (numeric UIDs: backend and frontend 10001, database 70, the UID of the postgres user in its image) |
| c: `readOnlyRootFilesystem: true` | every container; writable paths are `emptyDir`s with a size limit (`/tmp`, the database socket) and the database volume |
| c: `allowPrivilegeEscalation: false` | every container (also `privileged: false`) |
| c: `capabilities.drop` | `drop: ["ALL"]` in every container |
| d: NetworkPolicy, restrictive for inbound traffic | `networkpolicies.yaml`: default deny for ingress **and** egress, then only the flows below |

Pod Security Admission `restricted` enforces the settings of c on every pod of the namespace, so a manifest that weakens them is rejected by the cluster. Every pod also has `seccompProfile: RuntimeDefault`, resource requests and limits, and probes.

### Allowed network flows

```
 browser ──443──▶ Traefik ──8080──▶ frontend
                       │
                       └─────────8080──▶ backend ──5432──▶ postgres ◀──5432── db-migrate
 every pod ──53──▶ kube-dns                          (nothing else leaves the namespace)
```

| From | To | Port | Policy |
| :--- | :--- | :--- | :--- |
| Traefik | frontend | 8080 | `frontend-allow-ingress-controller` |
| Traefik | backend | 8080 | `backend-allow-ingress-controller` |
| backend | postgres | 5432 | `backend-allow-egress-postgres` and `postgres-allow-backend-and-migrate` |
| db-migrate | postgres | 5432 | `db-migrate-allow-egress-postgres` and `postgres-allow-backend-and-migrate` |
| every pod | kube-dns | 53 UDP/TCP | `allow-dns-egress` |
| everything else | | | denied by `default-deny-all` |

Consequences: the frontend cannot reach the database, the backend cannot reach the internet, and an unknown pod in the namespace can neither reach nor be reached by anything. kind's default network plugin does not enforce policies, therefore `make cni` installs Calico; `scripts/test-netpol.sh` (`make verify`) checks three blocked and three working connections and fails if any of them behaves differently.

## Secrets

Generated by `scripts/k8s-secrets.sh` (`make secrets`) with `openssl rand`, written to a private temporary directory, handed to `kubectl create secret`, and deleted. No value appears in the output, in the process list or in git.

| Secret | Keys | Used by |
| :--- | :--- | :--- |
| `db-credentials` | `db_superuser_password`, `db_owner_password`, `db_app_password` | the database pod (all three, as files); the migration job gets only the owner password |
| `backend-secrets` | `DATABASE_URL`, `MFA_ENCRYPTION_KEY` | the backend container, through `secretKeyRef` |
| `doctorholiday-tls` | `tls.crt`, `tls.key` | the ingress; self-signed for `doctorholiday.localhost`, valid 365 days |

An existing secret is never overwritten. To rotate one, delete it and run `make secrets`; for the database passwords that also means `make down`, because the passwords live in the database volume.

## Ingress

`/api` goes to the backend, `/` to the frontend. The backend's health probes `/healthz` and `/readyz` are **not** under `/api` and therefore not reachable from outside, on purpose; the frontend's own `/healthz` (only the word `ok`) is. HTTP is redirected to HTTPS at Traefik's entry point, and three middlewares (`middlewares.yaml`) add HSTS to every HTTPS response, a request limit per client IP and a body limit as defence in depth. Traefik runs in its own namespace `traefik` under Pod Security `restricted` (non-root, read-only filesystem, no hostPort: the kind node maps host ports 80 and 443 to its NodePorts) and watches only the namespace `doctorholiday` through a namespaced Role, so it cannot read other namespaces' secrets ([ADR-005](../../docs/architecture/adr/ADR-005-ingress-controller.md)).

## Images

`make images` builds both images from this checkout (tag `dev`, build arguments from `VERSION.txt` and `git rev-parse HEAD`) and loads them into the cluster with `kind load image-archive`; the manifests refer to them by name and the tag in `kustomization.yaml`. The signed images of the pipeline are used with `make up IMAGE_SOURCE=registry` (#43): `make registry-images` verifies both with cosign (`scripts/verify-image.sh`), `scripts/k8s-registry-overlay.sh` writes an overlay in `.cache/k8s-registry/` that replaces the images by the digests of `reports/images/<component>/image-ref.txt`, and the cluster pulls them from GHCR itself (nothing is loaded). With `GHCR_USER` and `GHCR_TOKEN` set a pull secret `ghcr-pull` is created and added to the Deployments, which is needed once the packages are private.

## Checks

- `make verify` (`scripts/test-netpol.sh`): two controls (the tool works), three connections that must be blocked, four that must work; the output goes to `reports/netpol/` (git-ignored, copied to the evidence by #44).
- Pod Security Admission: a privileged pod in the namespace is rejected by the API server (`violates PodSecurity "restricted:latest"`).
- `trivy config infrastructure/k8s` (Trivy 0.76.2): no HIGH and no CRITICAL finding. The remaining LOW and MEDIUM findings are explained: *no image tag* and *default namespace* (Kustomize adds tag and namespace when it renders), *untrusted registry* (GHCR is our registry), *ConfigMap with sensitive content* (a false positive on the keys `LOG_LEVEL` and `PORT`), and *UID/GID below 10000* for the database and its migration job (the `postgres` user of the image has UID 70).
- Unknown paths on the host answer with the SPA's `index.html` (a single-page app), so `https://doctorholiday.localhost/readyz` shows the HTML page, not the backend's readiness; the backend's probes stay inside the cluster.

## Known gaps

- **Images by tag, locally:** the local build is tagged `dev` (a build of this checkout, not a registry reference). The pipeline replaces the tag by the digest of the signed image (#43). The database image is pinned by digest.
- **Calico images by tag:** the upstream manifest references its images by tag, not by digest. The manifest itself is pinned by URL tag and SHA-256.
- **Traefik is ours to update:** its Deployment is a manifest in this repository (not an upstream bundle), so a new release means a new image digest in `infrastructure/kind/traefik.yaml` and, if the CRDs changed, a new URL and checksum in `versions.env`.
- **No TLS inside the cluster:** traffic from the ingress to the pods and from the backend to the database is plain, protected by the NetworkPolicies (TH-71, TH-74 in the threat model).
- **Self-signed certificate:** browsers warn once; there is no public CA for a local name.

## Troubleshooting

- `bind: address already in use` while creating the cluster: ports 80 or 443 are taken by another program on this machine. Stop it, or change `hostPort` in `infrastructure/kind/kind-config.yaml`.
- `make up` hangs at `wait`: `make status` and `make logs` show which pod is not Ready; a pod rejected by Pod Security shows the reason in `kubectl --context kind-doctorholiday -n doctorholiday get events`.
- Start over completely: `make down && make up`.
