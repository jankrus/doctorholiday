#!/usr/bin/env bash
# Supply-chain pinning check (SR-06, AGENTS.md rule 7; issue #31).
#
#   - every third-party GitHub Action in .github/workflows/ is pinned by a full 40-character
#     commit SHA and carries its version in a comment (`uses: owner/repo@<sha> # v1.2.3`);
#   - every external container image is pinned by a sha256 digest, in
#       * Dockerfiles (`Dockerfile`, `Dockerfile.prod`, `app.Dockerfile`, `Containerfile`):
#         `FROM` and `COPY --from`,
#       * YAML files (`image:` keys: compose.yaml, Kubernetes manifests, the kind config,
#         workflow containers and services),
#       * image variables in the Makefile, in `*.mk` and in shell scripts (`FOO_IMAGE=...`,
#         `FOO_IMAGE := ...`).
#
# What it does NOT see (listed in .github/workflows/README.md): images that are only named inside
# a command line (`docker run <image> ...`), and Kustomize `images:` entries (#38).
#
# Exit code 0 = all pinned, 1 = at least one mutable reference. Run from anywhere: `make
# check-pinning`, and in the `meta` job of the pipeline.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
failures=0

fail() {
  echo "::error::$1" >&2
  failures=$((failures + 1))
}

# ---- GitHub Actions -------------------------------------------------------------------------
shopt -s nullglob
workflows=(.github/workflows/*.yml .github/workflows/*.yaml)
for file in "${workflows[@]}"; do
  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    # `uses:` lines only (also `- uses:`); comments and other keys are skipped.
    [[ "$line" =~ ^[[:space:]]*-?[[:space:]]*uses:[[:space:]]*([^[:space:]#]+)([[:space:]]*#[[:space:]]*(.*))? ]] || continue
    ref="${BASH_REMATCH[1]}"
    comment="${BASH_REMATCH[3]:-}"
    # Local actions and reusable workflows of this repository are reviewed with the repository.
    [[ "$ref" == ./* ]] && continue
    if ! [[ "$ref" =~ @[0-9a-f]{40}$ ]]; then
      fail "$file:$line_no: '$ref' is not pinned by a full commit SHA"
    elif ! [[ "$comment" =~ ^v?[0-9]+(\.[0-9]+)* ]]; then
      fail "$file:$line_no: '$ref' has no version comment (# v1.2.3)"
    fi
  done < "$file"
done

# ---- Container images -----------------------------------------------------------------------
digest='@sha256:[0-9a-f]{64}'

check_image() { # file line_no image
  local file="$1" line_no="$2" image="$3"
  [[ "$image" == "scratch" ]] && return 0
  # A value built from a variable (`${IMAGE}`, `$(IMAGE)`) is checked where the variable is set.
  [[ "$image" == *'$'* ]] && return 0
  # `image: [frontend, backend]` is a build matrix, not an image reference.
  [[ "$image" == '['* || "$image" == '{'* ]] && return 0
  if ! [[ "$image" =~ $digest ]]; then
    fail "$file:$line_no: image '$image' is not pinned by a sha256 digest"
  fi
}

# Dockerfiles: Dockerfile, Dockerfile.*, *.Dockerfile, Containerfile, Containerfile.*
while IFS= read -r file; do
  declare -A stages=()
  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    if [[ "$line" =~ ^[[:space:]]*FROM[[:space:]]+(--[^[:space:]]+[[:space:]]+)*([^[:space:]]+)([[:space:]]+[Aa][Ss][[:space:]]+([^[:space:]]+))? ]]; then
      image="${BASH_REMATCH[2]}"
      stage="${BASH_REMATCH[4]:-}"
      # A reference to an earlier stage (FROM build) is not an external image.
      if [[ -z "${stages[$image]:-}" ]]; then
        check_image "$file" "$line_no" "$image"
      fi
      [[ -n "$stage" ]] && stages["$stage"]=1
    elif [[ "$line" =~ ^[[:space:]]*COPY[[:space:]]+.*--from=([^[:space:]]+) ]]; then
      source="${BASH_REMATCH[1]}"
      if [[ -z "${stages[$source]:-}" && "$source" =~ [:/] ]]; then
        check_image "$file" "$line_no" "$source"
      fi
    fi
  done < "$file"
  unset stages
done < <(git ls-files | grep -E '(^|/)(Dockerfile|Containerfile)([.][^/]*)?$|[.]Dockerfile$' | sort -u)

# YAML files: every `image:` key (compose, Kubernetes manifests, kind config, workflow containers).
while IFS= read -r file; do
  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    if [[ "$line" =~ ^[[:space:]]*-?[[:space:]]*image:[[:space:]]*[\"\']?([^\"\'[:space:]#]+) ]]; then
      check_image "$file" "$line_no" "${BASH_REMATCH[1]}"
    fi
  done < "$file"
done < <(git ls-files '*.yaml' '*.yml' | sort -u)

# Makefile, *.mk and shell scripts: variables named ...IMAGE that hold an image reference.
while IFS= read -r file; do
  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    if [[ "$line" =~ ^[[:space:]]*([A-Z0-9_]*IMAGE)[[:space:]]*:?=[[:space:]]*[\"\']?([^\"\'[:space:]#]+) ]]; then
      value="${BASH_REMATCH[2]}"
      # Only values that look like an image reference (registry path or tag), not flags or names.
      [[ "$value" =~ [:/] ]] && check_image "$file" "$line_no" "$value"
    fi
  done < "$file"
done < <(git ls-files 'Makefile' '*/Makefile' '*.mk' 'scripts/*.sh' | sort -u)

if ((failures > 0)); then
  echo "$failures mutable reference(s) found. Pin actions by commit SHA and images by digest." >&2
  exit 1
fi
echo "All actions and images are pinned."
