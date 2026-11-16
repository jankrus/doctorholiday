# infrastructure/kind

kind cluster of Doctor Holiday (issues #40, #41, #42).

- [`kind-config.yaml`](kind-config.yaml): one control-plane node (image pinned by digest), the default network plugin disabled so that Calico can enforce NetworkPolicies, ports 80 and 443 mapped to `127.0.0.1` only, label `ingress-ready=true`.
- [`versions.env`](versions.env): pinned versions, URLs and SHA-256 checksums of the upstream manifests that `make cni` (Calico) and `make ingress` (ingress-nginx) apply. A changed upstream file fails the run before anything is applied.

How to run it, the flows between the pods and the known gaps: [infrastructure/k8s/README.md](../k8s/README.md). The Makefile targets are in [`infrastructure/cluster.mk`](../cluster.mk).
