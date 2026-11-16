#!/usr/bin/env bash
# Builds one image, pushes it to the registry and records its immutable digest (issue #34, brief §3c
# and the intermediate instance of §3: the container registry).
#
#   scripts/build-image.sh frontend|backend
#
# What it does
#   1. builds <component>/Dockerfile with a pinned BuildKit (docker-container driver, so provenance
#      attestations work on every Docker), with --build-arg VERSION (content of VERSION.txt) and
#      --build-arg REVISION (full commit SHA) and SOURCE_DATE_EPOCH (time of the commit);
#   2. pushes it under the tags <VERSION> and <VERSION>-<shortsha>, never `latest`, with provenance
#      (mode=max);
#   3. reads the digest from the build metadata, checks with `imagetools inspect` that the registry
#      really has it, and checks that the pushed image carries the right labels (version and
#      revision; it fails on the local default `0.0.0-dev` or `unknown`);
#   4. writes reports/images/<component>/{digest.txt,image-ref.txt,metadata.json} (the brief's
#      submission files) and the output `<component>=sha256:...` for GitHub Actions.
# Everything downstream (signing, gate, deploy) uses image-ref.txt: the reference by digest.
#
# Environment
#   REGISTRY            registry and namespace, default ghcr.io/jankrus (a local registry for tests)
#   GITHUB_TOKEN, GITHUB_ACTOR   if both are set, the script logs in to ghcr.io (never put the token
#                       on a command line: it is read from the environment and piped)
#   REPORTS_DIR         default `reports`
#   BUILDX_DRIVER_OPTS  extra `--driver-opt` for the builder (tests against localhost: network=host)
set -euo pipefail

component="${1:-}"
case "$component" in
  frontend | backend) ;;
  *)
    echo "usage: $0 frontend|backend" >&2
    exit 2
    ;;
esac

cd "$(git rev-parse --show-toplevel)"

# Pinned BuildKit for the builder container (AGENTS.md rule 7); Dependabot updates it (#46).
BUILDKIT_IMAGE="moby/buildkit:v0.34.1@sha256:99368f3e46177c6405b9740e4461d91cee004128daeecca78d4ceac50ec1da5c"

registry="${REGISTRY:-ghcr.io/jankrus}"
version="$(tr -d '[:space:]' < VERSION.txt)"
revision="$(git rev-parse HEAD)"
short_sha="$(git rev-parse --short=7 HEAD)"
SOURCE_DATE_EPOCH="$(git log -1 --pretty=%ct)"
export SOURCE_DATE_EPOCH
name="$registry/doctorholiday-$component"
out="${REPORTS_DIR:-reports}/images/$component"
mkdir -p "$out"

if command -v python3 > /dev/null 2>&1 && python3 -c 'pass' > /dev/null 2>&1; then
  python=python3
else
  python=python
fi

if [[ "$version" == "0.0.0-dev" || ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  echo "VERSION.txt does not hold a release version: '$version'" >&2
  exit 1
fi

if [[ -n "${GITHUB_TOKEN:-}" && -n "${GITHUB_ACTOR:-}" ]]; then
  printf '%s' "$GITHUB_TOKEN" | docker login ghcr.io --username "$GITHUB_ACTOR" --password-stdin > /dev/null
fi

builder="doctorholiday-builder"
if ! docker buildx inspect "$builder" > /dev/null 2>&1; then
  # shellcheck disable=SC2086 # BUILDX_DRIVER_OPTS is a list of --driver-opt arguments
  docker buildx create --name "$builder" --driver docker-container \
    --driver-opt "image=$BUILDKIT_IMAGE" ${BUILDX_DRIVER_OPTS:-} > /dev/null
fi

metadata="$out/metadata.json"
rm -f "$metadata"
echo "building $name:$version ($short_sha), SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
docker buildx build "$component" \
  --builder "$builder" \
  --file "$component/Dockerfile" \
  --tag "$name:$version" \
  --tag "$name:$version-$short_sha" \
  --build-arg "VERSION=$version" \
  --build-arg "REVISION=$revision" \
  --provenance=mode=max \
  --sbom=false \
  --metadata-file "$metadata" \
  --output type=image,push=true,rewrite-timestamp=true

digest="$("$python" scripts/report_stats.py buildx-digest "$metadata")"
ref="$name@$digest"

# The registry must know the digest, and the image must carry the labels of this commit.
docker buildx imagetools inspect "$ref" > /dev/null
inspect_json="$out/inspect.json"
docker buildx imagetools inspect "$ref" --format '{{json .Image}}' > "$inspect_json"
"$python" scripts/report_stats.py image-labels "$inspect_json" "$version" "$revision"

printf '%s\n' "$digest" > "$out/digest.txt"
printf '%s\n' "$ref" > "$out/image-ref.txt"
rm -f "$inspect_json"
echo "pushed $ref"
echo "tags: $version, $version-$short_sha"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then echo "$component=$digest" >> "$GITHUB_OUTPUT"; fi
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "| Image | Digest | Tags |"
    echo "| --- | --- | --- |"
    echo "| \`doctorholiday-$component\` | \`$digest\` | \`$version\`, \`$version-$short_sha\` |"
  } >> "$GITHUB_STEP_SUMMARY"
fi
