#!/usr/bin/env bash
# Builds the slides of the presentation (issue #53): docs/presentation/slides.md ->
# docs/presentation/slides.pptx (editable, with speaker notes) and slides.pdf (handout).
#
#   scripts/build-slides.sh
#
# Pandoc runs as a pinned container image (AGENTS.md rule 7), the same one as the documentation
# (scripts/build-report.sh). The diagrams are read from docs/architecture and docs/threat-model.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
export MSYS_NO_PATHCONV=1 # Git Bash on Windows must not rewrite the container paths

PANDOC_IMAGE="pandoc/extra:3.7.0.2-ubuntu@sha256:ec00abc3763a1da177f69b1ed360deda7846f39d0f9457217da63d2e1e60c475"

if command -v cygpath > /dev/null 2>&1; then
  MOUNT="$(cygpath -m "$PWD")"
else
  MOUNT="$PWD"
fi

user_args=()
if [[ "$(uname -s)" == "Linux" ]]; then
  user_args=(--user "$(id -u):$(id -g)")
fi

pandoc_run() {
  docker run --rm "${user_args[@]}" -e HOME=/tmp --tmpfs /tmp:exec \
    -v "$MOUNT:/data" -w /data/docs/presentation "$PANDOC_IMAGE" \
    --resource-path=.:../architecture:../threat-model "$@"
}

pandoc_run slides.md --from markdown --slide-level=1 --output slides.pptx

pandoc_run slides.md --from markdown --to beamer --slide-level=1 --output slides.pdf \
  --pdf-engine=xelatex \
  --variable aspectratio=169 --variable fontsize=10pt \
  --variable mainfont="DejaVu Sans" --variable monofont="DejaVu Sans Mono" \
  --variable colorlinks=true --variable linkcolor=blue --variable urlcolor=blue

echo "wrote docs/presentation/slides.pptx and docs/presentation/slides.pdf"
