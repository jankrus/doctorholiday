#!/usr/bin/env bash
# Verifies the signature and the SBOM attestation of one image with the committed public key
# (issue #35; the quality gate #36 and the deployment #43 call it too). Exit code 1 if the image is
# not signed, the signature is invalid or the attestation is missing.
#
#   scripts/verify-image.sh frontend|backend              reference from reports/images/<c>/image-ref.txt
#   scripts/verify-image.sh --ref <image@sha256:...> <c>  verify a given reference
#
# Output: reports/signing/<component>/verify-<c>.json, verify-attestation-<c>.json, tree-<c>.txt
# and public-key-fingerprint-<c>.txt (evidence, brief §7a-v-6). The public key is
# infrastructure/signing/cosign.pub; nothing secret is needed.
#
# Environment
#   COSIGN        the cosign command, default `cosign`
#   COSIGN_PUBLIC_KEY   default infrastructure/signing/cosign.pub
#   REPORTS_DIR   default `reports`
set -euo pipefail

ref=""
if [[ "${1:-}" == "--ref" ]]; then
  ref="${2:-}"
  shift 2 || true
fi
component="${1:-}"
case "$component" in
  frontend | backend) ;;
  *)
    echo "usage: $0 [--ref <image@sha256:...>] frontend|backend" >&2
    exit 2
    ;;
esac

cd "$(git rev-parse --show-toplevel)"
cosign="${COSIGN:-cosign}"
reports="${REPORTS_DIR:-reports}"
key="${COSIGN_PUBLIC_KEY:-infrastructure/signing/cosign.pub}"
out="$reports/signing/$component"

if [[ -z "$ref" ]]; then
  ref_file="$reports/images/$component/image-ref.txt"
  [[ -s "$ref_file" ]] || { echo "missing $ref_file" >&2; exit 1; }
  ref="$(tr -d '[:space:]' < "$ref_file")"
fi
[[ "$ref" =~ @sha256:[0-9a-f]{64}$ ]] || { echo "not a reference by digest: $ref" >&2; exit 1; }
[[ -s "$key" ]] || { echo "missing public key $key" >&2; exit 1; }

mkdir -p "$out"
status=0

# Fingerprint of the public key: what the signatures are checked against.
if command -v sha256sum > /dev/null 2>&1; then
  fingerprint="$(sha256sum "$key" | cut -d' ' -f1)"
else
  fingerprint="$(shasum -a 256 "$key" | cut -d' ' -f1)"
fi
printf 'sha256:%s  %s\n' "$fingerprint" "$key" > "$out/public-key-fingerprint-$component.txt"

echo "Verifying the signature of $ref"
if ! "$cosign" verify --key "$key" --insecure-ignore-tlog=true "$ref" > "$out/verify-$component.json"; then
  echo "SIGNATURE INVALID OR MISSING: $ref" >&2
  status=1
fi

echo "Verifying the SBOM attestation of $ref"
if ! "$cosign" verify-attestation --key "$key" --type cyclonedx --insecure-ignore-tlog=true "$ref" > "$out/verify-attestation-$component.json"; then
  echo "SBOM ATTESTATION INVALID OR MISSING: $ref" >&2
  status=1
fi

# Shows the signature and the attestation as stored next to the image (acceptance of #35).
"$cosign" tree "$ref" > "$out/tree-$component.txt" 2>&1 || true

if [[ $status -eq 0 ]]; then
  echo "OK: signature and SBOM attestation of $ref verified with $key"
fi
exit $status
