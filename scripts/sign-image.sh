#!/usr/bin/env bash
# Signs one image by digest with cosign and attaches its SBOM as an attestation (issue #35, brief
# §3d). Key-based, because the submission needs the public key and a signature bundle per image.
#
#   COSIGN_PRIVATE_KEY=... COSIGN_PASSWORD=... scripts/sign-image.sh frontend|backend
#
# Input
#   reports/images/<component>/image-ref.txt   the image by digest (written by build-image.sh)
#   reports/sbom/sbom-<component>-*.cdx.json   its CycloneDX SBOM (written by scan.sh sbom)
# Output
#   reports/signing/<component>/signature-<component>.bundle and attestation-<component>.bundle
#   (the signature and the SBOM attestation as Sigstore bundles, kept for evidence and submission)
#
# The private key and its password are read from the environment of this process only; they are
# never put on a command line, in a file or in the output. Both secrets are masked by GitHub.
#
# Transparency log: no upload to the public Rekor log. cosign 3 wants that stated as a signing
# config without log services (infrastructure/signing/signing-config.json), see deviations.md D-10.
# Verification afterwards: scripts/verify-image.sh.
#
# Environment
#   COSIGN                  the cosign command, default `cosign`
#   COSIGN_SIGNING_CONFIG   default infrastructure/signing/signing-config.json
#   REPORTS_DIR             default `reports`
set -euo pipefail

component="${1:-}"
case "$component" in
  frontend | backend) ;;
  *)
    echo "usage: $0 frontend|backend" >&2
    exit 2
    ;;
esac
: "${COSIGN_PRIVATE_KEY:?COSIGN_PRIVATE_KEY is required}"
: "${COSIGN_PASSWORD:?COSIGN_PASSWORD is required}"

cd "$(git rev-parse --show-toplevel)"
cosign="${COSIGN:-cosign}"
reports="${REPORTS_DIR:-reports}"
signing_config="${COSIGN_SIGNING_CONFIG:-infrastructure/signing/signing-config.json}"
ref_file="$reports/images/$component/image-ref.txt"
out="$reports/signing/$component"

[[ -s "$signing_config" ]] || { echo "missing $signing_config" >&2; exit 1; }
[[ -s "$ref_file" ]] || { echo "missing $ref_file: build the image first" >&2; exit 1; }
ref="$(tr -d '[:space:]' < "$ref_file")"
# Only ever sign a digest: a tag can be moved after the signature.
[[ "$ref" =~ @sha256:[0-9a-f]{64}$ ]] || { echo "not a reference by digest: $ref" >&2; exit 1; }

shopt -s nullglob
sboms=("$reports"/sbom/sbom-"$component"-*.cdx.json)
shopt -u nullglob
[[ ${#sboms[@]} -eq 1 ]] || { echo "expected exactly one SBOM for $component in $reports/sbom, found ${#sboms[@]}" >&2; exit 1; }
sbom="${sboms[0]}"

mkdir -p "$out"
rm -f "$out/signature-$component.bundle" "$out/attestation-$component.bundle"

echo "Signing $ref"
"$cosign" sign --yes --key env://COSIGN_PRIVATE_KEY --signing-config "$signing_config" \
  --bundle "$out/signature-$component.bundle" "$ref"

echo "Attesting the SBOM $sbom"
"$cosign" attest --yes --key env://COSIGN_PRIVATE_KEY --signing-config "$signing_config" \
  --type cyclonedx --predicate "$sbom" \
  --bundle "$out/attestation-$component.bundle" "$ref"

echo "Signed and attested $ref"
