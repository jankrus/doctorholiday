#!/usr/bin/env bash
# Sort the reports of one pipeline run into the evidence tree (issue #44, exam brief §7a-v).
#
#   scripts/collect-evidence.sh <artifacts-dir> <evidence-dir> <prefix>
#
#   <artifacts-dir>  the downloaded workflow artifacts, one directory per artifact:
#                    sbom/ sast/ sca/ secrets/ signing/ gate/ image-<image>/ run-logs/
#   <evidence-dir>   destination, normally `evidence/`
#   <prefix>         names this run, e.g. `0042-a1b2c3d` (run number, short commit)
#
# Result: <evidence-dir>/<image>/<type>/<prefix>-<file> for both images (frontend, backend) and
# the types run, sast, sbom, sca, secrets, signing. Files that name an image (`...-backend...`,
# `...-frontend...`) go to that image; files that belong to the whole repository (the Gitleaks
# report, the run logs, the job summary) go to both. Existing files are never overwritten, so
# evidence of earlier runs stays. Missing artifacts are skipped, a blocked run is evidence too.
#
# The same script is used by the pipeline (`evidence` job) and by `make evidence` on a laptop.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <artifacts-dir> <evidence-dir> <prefix>" >&2
  exit 2
fi
artifacts="$1"
evidence="$2"
prefix="$3"
[[ "$prefix" =~ ^[0-9A-Za-z._-]+$ ]] || { echo "invalid prefix: $prefix" >&2; exit 2; }
[[ -d "$artifacts" ]] || { echo "no such directory: $artifacts" >&2; exit 2; }

images=(frontend backend)
types=(run sast sbom sca secrets signing)

for image in "${images[@]}"; do
  for type in "${types[@]}"; do
    mkdir -p "$evidence/$image/$type"
  done
done

copied=0

# put <source file> <image> <type>: copy, keeping the name, never overwriting.
put() {
  local src="$1" image="$2" type="$3" dest
  dest="$evidence/$image/$type/$prefix-$(basename "$src")"
  if [[ -e "$dest" ]]; then
    echo "keep   $dest (exists)"
    return
  fi
  cp -- "$src" "$dest"
  copied=$((copied + 1))
  echo "add    $dest"
}

# sort_dir <artifact directory> <type>: files naming an image go there, the others to both.
sort_dir() {
  local dir="$artifacts/$1" type="$2" file name image matched
  [[ -d "$dir" ]] || { echo "skip   $1 (no such artifact)"; return; }
  while IFS= read -r -d '' file; do
    name="$(basename "$file")"
    matched=false
    for image in "${images[@]}"; do
      if [[ "$name" == *"-$image-"* || "$name" == *"-$image."* || "$name" == "$image-"* ]]; then
        put "$file" "$image" "$type"
        matched=true
      fi
    done
    if [[ "$matched" == false ]]; then
      for image in "${images[@]}"; do put "$file" "$image" "$type"; done
    fi
  done < <(find "$dir" -type f -print0 | sort -z)
}

sort_dir sbom sbom
sort_dir sast sast
sort_dir sca sca
sort_dir secrets secrets
sort_dir signing signing
# Gate result and job logs describe the whole run; the image artifacts (digest, reference by
# digest, build provenance) belong to one image each.
sort_dir gate run
sort_dir run-logs run
for image in "${images[@]}"; do
  dir="$artifacts/image-$image"
  if [[ -d "$dir" ]]; then
    while IFS= read -r -d '' file; do
      put "$file" "$image" run
    done < <(find "$dir" -type f -print0 | sort -z)
  else
    echo "skip   image-$image (no such artifact)"
  fi
done

echo "Collected $copied file(s) for run $prefix into $evidence/"
