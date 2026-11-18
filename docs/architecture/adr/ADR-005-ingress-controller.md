# ADR-005: Ingress Controller (Traefik instead of ingress-nginx)

- **Status:** Accepted; replaces the choice of `ingress-nginx` in [ADR-001 §3.3](ADR-001-tech-stack.md).
- **Issue:** [#40 – Configure the ingress with TLS for the kind cluster](https://github.com/jankrus/doctorholiday/issues/40)
- **Raised by:** review of PR #105 (the first version kept ingress-nginx and justified it as accepted risk).

## 1. Context
`make up` has to roll out an ingress (brief §7). ADR-001 named `ingress-nginx` because the kind documentation uses it. The first implementation followed that, and checked the project: the last release of the ingress-nginx controller is `controller-v1.15.1` from 2026-03-19, and the upstream project announced its retirement for March 2026, so security fixes no longer arrive. A security-by-design project should not put an unmaintained component at its edge, the only part reachable from the browser. Staying was a choice made by habit, not a requirement: nothing in the brief names the controller.

## 2. Considered Options
*   **Option A: ingress-nginx (kept)**
    *   *Pros:* single upstream manifest for kind, annotations for rate limit and body size, no further work.
    *   *Cons:* no upstream release since 2026-03-19, so future vulnerabilities stay open; it had to be listed as an accepted risk.
*   **Option B: Traefik**
    *   *Pros:* actively maintained; understands the normal `Ingress` resource, so `ingress.yaml` stays portable; one small Deployment that we can write and review ourselves; runs without root, without a hostPort and with a read-only filesystem; can be limited to one namespace with a namespaced Role; HSTS, rate limit and body limit as `Middleware` objects.
    *   *Cons:* extra CRDs for the middlewares (pinned by checksum); different annotations than ingress-nginx.
*   **Option C: Gateway API with Envoy Gateway**
    *   *Pros:* the direction of the Kubernetes project; maintained.
    *   *Cons:* `Gateway` and `HTTPRoute` instead of `Ingress`, more CRDs and moving parts, the largest change shortly before the submission.

## 3. Decision Outcome
We use **Traefik** (Option B), installed by `make ingress` from `infrastructure/kind/traefik.yaml`.

- **Image:** `traefik:v3.7.17`, pinned by digest in the manifest. The Traefik CRDs come from the upstream release tag and are verified against a SHA-256 in `infrastructure/kind/versions.env` before they are applied.
- **Network:** the kind node maps the host's `127.0.0.1:80` and `:443` to the NodePorts `30080` and `30443`; Traefik listens on unprivileged ports inside the pod. HTTP is redirected to HTTPS (permanent) at the entry point.
- **Hardening:** own namespace `traefik` under Pod Security `restricted` (possible because there is no hostPort), non-root, read-only root filesystem, no capabilities.
- **Least privilege on the API:** Traefik watches only the namespace `doctorholiday`. A namespaced `Role` there gives it read access to services, secrets, endpoint slices, ingresses and its own CRDs; the only cluster-wide rights are read-only lists of `IngressClass` and `Nodes` (its Kubernetes provider does not start without them). A compromised controller therefore cannot read the secrets of other namespaces (this mitigates TH-16 of the threat model).
- **Middlewares** (`infrastructure/k8s/middlewares.yaml`): HSTS, a rate limit of 50 requests per second per client IP and a body limit of 32 KiB. They replace the ingress-nginx annotations.

## 4. Consequences
*   **Security (Pros):** a maintained edge component; smaller privileges than ingress-nginx's default (cluster-wide secret access); the controller runs under `restricted`. The deviation entry about an unmaintained controller (D-08 of the first version) is not needed any more.
*   **Operations (Cons):** an additional namespace and a set of CRDs; the Traefik manifest is ours and has to be updated by hand when a new release appears (Dependabot proposes the image digest, #46).
*   **Documentation:** architecture, threat model (P1) and diagrams name Traefik; ADR-001 §3.3 keeps its text with a pointer to this ADR.
