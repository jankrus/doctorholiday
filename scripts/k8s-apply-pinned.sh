#!/usr/bin/env bash
# Downloads an upstream Kubernetes manifest, verifies its SHA-256 and applies it (issues #40, #41).
#
#   scripts/k8s-apply-pinned.sh <kube-context> <url> <sha256> [server-side]
#
# The file is checked BEFORE anything is applied; a different checksum (a changed or tampered
# upstream file) stops the run with exit code 1. The download lives in a private temporary
# directory that is removed afterwards. `server-side` applies with server-side apply, which large
# files such as the Traefik CRDs need (client-side apply stores the whole file in an annotation).
set -euo pipefail

context="${1:?usage: $0 <kube-context> <url> <sha256>}"
url="${2:?usage: $0 <kube-context> <url> <sha256>}"
expected="${3:?usage: $0 <kube-context> <url> <sha256>}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
file="$tmp/manifest.yaml"

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$file" "$url"

if command -v sha256sum > /dev/null 2>&1; then
  actual="$(sha256sum "$file" | cut -d ' ' -f 1)"
else
  actual="$(shasum -a 256 "$file" | cut -d ' ' -f 1)"
fi

if [[ "$actual" != "$expected" ]]; then
  echo "checksum mismatch for $url" >&2
  echo "  expected $expected" >&2
  echo "  got      $actual" >&2
  exit 1
fi

if [[ "${4:-}" == "server-side" ]]; then
  kubectl --context "$context" apply --server-side --force-conflicts --filename "$file"
else
  kubectl --context "$context" apply --filename "$file"
fi
