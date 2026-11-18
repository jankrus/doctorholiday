# Cluster targets of the root Makefile (issues #37-#42): `make up` is the blueprint of the whole
# project, brief §7 "Hinweis Makefile": start the cluster, create the namespace, roll out the
# ingress, load the images, apply the manifests, wait until everything is healthy, print "Ready".
#
# Every target is idempotent: `make up` twice changes nothing the second time. All kubectl calls use
# the context of this cluster (kind-doctorholiday), so another cluster on this machine is never
# touched. Included by the Makefile in the repository root.

include infrastructure/kind/versions.env

CLUSTER := doctorholiday
CTX := kind-$(CLUSTER)
NS := doctorholiday
KUBECTL := kubectl --context $(CTX)
KUBECTL_NS := $(KUBECTL) --namespace $(NS)
APP_URL := https://doctorholiday.localhost
# Local build tags of the images made by `make images` (loaded into the cluster, never pulled), so
# they are not pinned by digest like a registry reference; the pipeline sets digests in #43.
BACKEND_LOCAL_REF := ghcr.io/jankrus/doctorholiday-backend:dev
FRONTEND_LOCAL_REF := ghcr.io/jankrus/doctorholiday-frontend:dev
# local = build the images from this checkout; the pipeline's signed images (ghcr) follow with #34, #35.
IMAGE_SOURCE ?= local
# No provenance attestation in the local image: `kind load` cannot import an image index that carries
# one. Docker versions without BuildKit do not know the flag at all, so it is only passed if it exists.
BUILD_FLAGS := $(shell docker build --help 2> /dev/null | grep -q -e --provenance && echo --provenance=false)

# The targets of `up` must run in this order.
.NOTPARALLEL:

up: check-tools cluster cni namespace ingress secrets db-config images deploy wait ## Create the kind cluster and deploy the app; prints Ready (#42)
	@echo
	@echo "Ready"
	@echo "  $(APP_URL)  (self-signed certificate: accept the browser warning or use curl -k)"
	@echo "  The first login becomes the admin: register and log in right now (README, #15)."

down: ## Delete the kind cluster and everything in it (#42)
	@if kind get clusters 2> /dev/null | grep -qx $(CLUSTER); then kind delete cluster --name $(CLUSTER); else echo "cluster $(CLUSTER) does not exist"; fi

check-tools: ## Check that the tools for `make up` are installed (#42)
	@missing=0; \
	for tool in docker kind kubectl openssl curl; do \
		if ! command -v $$tool > /dev/null 2>&1; then echo "missing tool: $$tool"; missing=1; fi; \
	done; \
	[ $$missing -eq 0 ] || { echo "Install the missing tools, see infrastructure/k8s/README.md."; exit 1; }
	@docker info > /dev/null 2>&1 || { echo "Docker is installed but its daemon is not running."; exit 1; }
	@echo "kind $$(kind version -q 2> /dev/null || kind version | head -1) (pinned: $(KIND_VERSION))"
	@echo "kubectl $$(kubectl version --client -o json 2> /dev/null | sed -n 's/.*"gitVersion": "\(.*\)".*/\1/p' | head -1)"

cluster: ## Create the kind cluster if it does not exist (#40)
	@if kind get clusters 2> /dev/null | grep -qx $(CLUSTER); then \
		echo "cluster $(CLUSTER) already exists"; \
	else \
		kind create cluster --config infrastructure/kind/kind-config.yaml; \
	fi

cni: ## Install Calico, which enforces NetworkPolicies (kindnet does not) (#41)
	scripts/k8s-apply-pinned.sh $(CTX) "$(CALICO_URL)" "$(CALICO_SHA256)"
	$(KUBECTL) --namespace kube-system rollout status daemonset/calico-node --timeout=300s
	$(KUBECTL) wait --for=condition=Ready nodes --all --timeout=300s

# Needs the namespace: Traefik's Role and RoleBinding live there (it may only read that namespace).
ingress: namespace ## Install the ingress controller Traefik and wait for it (#40)
	scripts/k8s-apply-pinned.sh $(CTX) "$(TRAEFIK_CRDS_URL)" "$(TRAEFIK_CRDS_SHA256)" server-side
	$(KUBECTL) wait --for=condition=Established crd/middlewares.traefik.io --timeout=120s
	$(KUBECTL) apply --filename infrastructure/kind/traefik.yaml
	$(KUBECTL) --namespace traefik rollout status deployment/traefik --timeout=300s

namespace: ## Create the namespace with Pod Security `restricted` (#37)
	$(KUBECTL) apply --filename infrastructure/k8s/namespace.yaml

secrets: namespace ## Generate the secrets at deploy time, never overwriting existing ones (#30)
	scripts/k8s-secrets.sh $(CTX) $(NS)

# The init script and the migrations are ConfigMaps made from the files in the repository, the
# only copy of them (Kustomize cannot read files outside infrastructure/k8s).
db-config: namespace ## ConfigMaps for the database init script and the migrations (#39)
	$(KUBECTL_NS) create configmap postgres-init --from-file=infrastructure/postgres/init/00-roles.sh --dry-run=client --output=yaml | $(KUBECTL_NS) apply --filename -
	$(KUBECTL_NS) create configmap db-migrate-script --from-file=infrastructure/postgres/migrate.sh --dry-run=client --output=yaml | $(KUBECTL_NS) apply --filename -
	$(KUBECTL_NS) create configmap db-migrations --from-file=backend/migrations --dry-run=client --output=yaml | $(KUBECTL_NS) apply --filename -
	$(KUBECTL_NS) label configmap postgres-init db-migrate-script db-migrations app.kubernetes.io/part-of=doctorholiday --overwrite

images: ## Build the images and load them into the cluster (#28, #42)
	@if [ "$(IMAGE_SOURCE)" != "local" ]; then \
		echo "IMAGE_SOURCE=$(IMAGE_SOURCE) is not implemented yet: signed images from GHCR need #34 and #35."; \
		exit 1; \
	fi
	docker build $(BUILD_FLAGS) --tag $(BACKEND_LOCAL_REF) --build-arg VERSION=$$(tr -d '[:space:]' < VERSION.txt) --build-arg REVISION=$$(git rev-parse HEAD) backend
	docker build $(BUILD_FLAGS) --tag $(FRONTEND_LOCAL_REF) --build-arg VERSION=$$(tr -d '[:space:]' < VERSION.txt) --build-arg REVISION=$$(git rev-parse HEAD) frontend
	@mkdir -p .cache
	docker save --output .cache/images.tar $(BACKEND_LOCAL_REF) $(FRONTEND_LOCAL_REF)
	kind load image-archive .cache/images.tar --name $(CLUSTER)

# A finished Job cannot be changed, so it is deleted first; migrate.sh applies each migration once.
deploy: ## Apply the manifests and run the database migrations (#37-#41)
	$(KUBECTL_NS) delete job db-migrate --ignore-not-found
	$(KUBECTL) apply --kustomize infrastructure/k8s
	$(KUBECTL_NS) wait --for=condition=complete job/db-migrate --timeout=300s

wait: ## Wait until database, backend and frontend are Ready and the app answers (#42)
	$(KUBECTL_NS) rollout status statefulset/postgres --timeout=300s
	$(KUBECTL_NS) rollout status deployment/backend --timeout=300s
	$(KUBECTL_NS) rollout status deployment/frontend --timeout=300s
	$(KUBECTL_NS) wait --for=condition=Ready pod --selector='app.kubernetes.io/name in (postgres,backend,frontend)' --timeout=300s
	@for i in $$(seq 1 30); do \
		if curl --silent --insecure --fail --output /dev/null --max-time 5 $(APP_URL)/; then echo "$(APP_URL) answers"; exit 0; fi; \
		sleep 2; \
	done; \
	echo "$(APP_URL) did not answer in time"; exit 1

status: ## Show the state of the deployment (#42)
	$(KUBECTL_NS) get pods,statefulsets,services,ingress,networkpolicies,persistentvolumeclaims,jobs

logs: ## Show the recent logs of all application containers (#42)
	$(KUBECTL_NS) logs --selector=app.kubernetes.io/part-of=doctorholiday --all-containers --prefix --tail=50 --ignore-errors

verify: ## Prove that the NetworkPolicies are enforced (#41)
	scripts/test-netpol.sh $(CTX) $(NS)
