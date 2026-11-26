#!/usr/bin/env bash
# Builds the PDF of the final documentation (issue #50): docs/report/documentation.md ->
# docs/report/documentation.pdf, for the submission package (brief §7, folder Dokumentation).
#
#   scripts/build-report.sh
#
# Pandoc with XeLaTeX runs as a pinned container image (AGENTS.md rule 7), so the PDF looks the same
# on every machine. The images of the diagrams are read from docs/architecture and
# docs/threat-model; links to other Markdown files stay as text in the PDF.
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

docker run --rm "${user_args[@]}" -e HOME=/tmp --tmpfs /tmp:exec \
  -v "$MOUNT:/data" -w /data/docs/report "$PANDOC_IMAGE" \
  documentation.md --output documentation.pdf \
  --from gfm --pdf-engine=xelatex --toc --toc-depth=2 --number-sections=false \
  --metadata title="Doctor Holiday: Abschlussdokumentation" \
  --metadata lang=de-DE \
  --variable geometry:margin=2.2cm --variable fontsize=10pt \
  --variable mainfont="DejaVu Serif" --variable sansfont="DejaVu Sans" --variable monofont="DejaVu Sans Mono" \
  --variable colorlinks=true --variable linkcolor=blue --variable urlcolor=blue \
  --resource-path=.:../architecture:../threat-model

echo "wrote docs/report/documentation.pdf"
