# infrastructure/kind

kind cluster of Doctor Holiday (issues #40, #41, #42).

- [`kind-config.yaml`](kind-config.yaml): one control-plane node (image pinned by digest), the default network plugin disabled so that Calico can enforce NetworkPolicies, ports 80 and 443 mapped to `127.0.0.1` only (to the NodePorts of the ingress controller).
- [`traefik.yaml`](traefik.yaml): the ingress controller Traefik ([ADR-005](../../docs/architecture/adr/ADR-005-ingress-controller.md)): own namespace under Pod Security `restricted`, non-root, read-only filesystem, image pinned by digest, a namespaced Role so that it can only read the application's namespace.
- [`versions.env`](versions.env): pinned versions, URLs and SHA-256 checksums of the upstream files that `make cni` (Calico manifest) and `make ingress` (Traefik CRDs) apply. A changed upstream file fails the run before anything is applied.

How to run it, the flows between the pods and the known gaps: [infrastructure/k8s/README.md](../k8s/README.md). The Makefile targets are in [`infrastructure/cluster.mk`](../cluster.mk).
