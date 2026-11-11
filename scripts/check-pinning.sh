#!/usr/bin/env bash
# Supply-chain pinning check (SR-06, AGENTS.md rule 7; issue #31).
#
#   - every third-party GitHub Action in .github/workflows/ is pinned by a full 40-character
#     commit SHA and carries its version in a comment (`uses: owner/repo@<sha> # v1.2.3`);
#   - every external image in a Dockerfile (FROM, COPY --from) and in compose.yaml is pinned by a
#     sha256 digest.
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
  if ! [[ "$image" =~ $digest ]]; then
    fail "$file:$line_no: image '$image' is not pinned by a sha256 digest"
  fi
}

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
done < <(git ls-files '*Dockerfile' '**/Dockerfile' | sort -u)

if [[ -f compose.yaml ]]; then
  line_no=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    if [[ "$line" =~ ^[[:space:]]*image:[[:space:]]*([^[:space:]#]+) ]]; then
      check_image compose.yaml "$line_no" "${BASH_REMATCH[1]}"
    fi
  done < compose.yaml
fi

if ((failures > 0)); then
  echo "$failures mutable reference(s) found. Pin actions by commit SHA and images by digest." >&2
  exit 1
fi
echo "All actions and images are pinned."
