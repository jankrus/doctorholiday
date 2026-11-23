#!/usr/bin/env bash
# Creates the image pull secret `ghcr-pull` for GHCR in the namespace (issue #43), so the cluster
# can pull the images even when the repository and its packages are private.
#
#   GHCR_USER=... GHCR_TOKEN=... scripts/k8s-pull-secret.sh <kube-context> <namespace>
#
# The token (the pipeline's GITHUB_TOKEN, or a personal access token with read:packages) comes from
# the environment, never from the command line. The Docker config is written to a private temporary
# file that is removed at once. The secret lives only in the (ephemeral) cluster.
set -euo pipefail

context="${1:?usage: $0 <kube-context> <namespace>}"
namespace="${2:?usage: $0 <kube-context> <namespace>}"
: "${GHCR_USER:?GHCR_USER is not set}"
: "${GHCR_TOKEN:?GHCR_TOKEN is not set}"

umask 077
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
auth="$(printf '%s:%s' "$GHCR_USER" "$GHCR_TOKEN" | base64 | tr -d '\n')"
printf '{"auths":{"ghcr.io":{"auth":"%s"}}}' "$auth" > "$tmp/config.json"

kubectl --context "$context" --namespace "$namespace" create secret generic ghcr-pull \
  --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson="$tmp/config.json" \
  --dry-run=client --output=yaml |
  kubectl --context "$context" --namespace "$namespace" apply --filename -
