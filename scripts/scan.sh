#!/usr/bin/env bash
# SBOM and security scans of the source trees (issues #32 and #33; SR-06, SR-03, SR-05).
#
#   scripts/scan.sh sbom      CycloneDX SBOM per component (Syft), validated
#   scripts/scan.sh sast      static analysis (Semgrep), JSON + SARIF per component
#   scripts/scan.sh sca       known vulnerabilities in the lockfiles (Trivy fs), JSON + SARIF
#   scripts/scan.sh secrets   secrets in the whole git history (Gitleaks), JSON + SARIF
#
# The pipeline calls exactly this script, so every report can be reproduced on a laptop with
# Docker. All tools run as pinned container images (AGENTS.md rule 7). The scans report findings
# and exit 0: the quality gate (#36) decides what blocks. Reports go to `reports/<kind>/` (git-
# ignored); the evidence job (#44) copies them to `evidence/<image>/`.
#
# Environment: VERSION and SHORT_SHA name the SBOM files (default: VERSION.txt, HEAD);
# REPORTS_DIR overrides `reports`. In GitHub Actions the script also writes `findings=<n>` (or
# `components=<n>`) to $GITHUB_OUTPUT and a table to $GITHUB_STEP_SUMMARY.
#
# Not here yet: the scans of the built images (SBOM per digest, `trivy image`), they need the
# images from #34.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
export MSYS_NO_PATHCONV=1 # Git Bash on Windows must not rewrite the container paths

# ---- Pinned tool images (tag for humans, digest for Docker); Dependabot updates them (#46) ----
SYFT_IMAGE="anchore/syft:v1.57.1@sha256:03215d0e98b661d0ecbc8575dbc14d65be1743b5de5df6410aecb7e80f95b060"
CYCLONEDX_IMAGE="cyclonedx/cyclonedx-cli:0.33.1@sha256:252c2e26f468c25fea1e63ecde1bc3198ad6e9dbb57f5ed3236bddcb2281b3a7"
SEMGREP_IMAGE="semgrep/semgrep:1.185.0@sha256:67518c174185a2043fdbed16c70631b79209499b3671178e7194379b48295a0d"
TRIVY_IMAGE="aquasec/trivy:0.76.2@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"
GITLEAKS_IMAGE="ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"

COMPONENTS=(frontend backend)
VERSION="${VERSION:-$(tr -d '[:space:]' < VERSION.txt)}"
SHORT_SHA="${SHORT_SHA:-$(git rev-parse --short=7 HEAD)}"
REPORTS="${REPORTS_DIR:-reports}"

if command -v python3 > /dev/null 2>&1 && python3 -c 'pass' > /dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

if command -v cygpath > /dev/null 2>&1; then
  MOUNT="$(cygpath -m "$PWD")" # Git Bash: C:/path
else
  MOUNT="$PWD"
fi

# On Linux the tools run as the calling user, so the reports are not owned by root.
user_args=()
if [[ "$(uname -s)" == "Linux" ]]; then
  user_args=(--user "$(id -u):$(id -g)")
fi

# docker_run <image> <args...>: repository mounted at /src, nothing else; HOME on a tmpfs.
docker_run() {
  local image="$1"
  shift
  docker run --rm "${user_args[@]}" -e HOME=/tmp --tmpfs /tmp:exec \
    -v "$MOUNT:/src" -w /src "$image" "$@"
}

stats() { "$PYTHON" scripts/report_stats.py "$@"; }

output() { # key value: step output and summary line
  echo "$1=$2"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then echo "$1=$2" >> "$GITHUB_OUTPUT"; fi
}

summary() {
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then echo "$1" >> "$GITHUB_STEP_SUMMARY"; fi
}

sbom() {
  mkdir -p "$REPORTS/sbom"
  local total=0 component file count
  summary "| Component | SBOM | Components |"
  summary "| --- | --- | --- |"
  for component in "${COMPONENTS[@]}"; do
    file="$REPORTS/sbom/sbom-$component-$VERSION-$SHORT_SHA.cdx.json"
    docker_run "$SYFT_IMAGE" scan "dir:/src/$component" \
      --source-name "doctorholiday-$component" --source-version "$VERSION" \
      --exclude "**/node_modules/**" --exclude "**/.venv/**" \
      -o "cyclonedx-json=/src/$file" -q
    # Schema validation by the CycloneDX CLI, then a plausibility check of our own.
    docker_run "$CYCLONEDX_IMAGE" validate --input-file "/src/$file" --input-format json \
      --fail-on-errors > /dev/null
    count="$(stats sbom "$file")"
    total=$((total + count))
    echo "$file: $count components"
    summary "| $component | \`$(basename "$file")\` | $count |"
  done
  output components "$total"
}

sast() {
  mkdir -p "$REPORTS/sast"
  local component total=0 count
  summary "| Component | Semgrep findings |"
  summary "| --- | --- |"
  for component in "${COMPONENTS[@]}"; do
    local packs=(--config p/default --config p/owasp-top-ten --config p/secrets)
    case "$component" in
      # The Python 3.7 compatibility rule flags `importlib.resources`; the backend runs on 3.12 only.
      # Listed in docs/report/deviations.md.
      backend)
        packs+=(--config p/python --config .semgrep/
          --exclude-rule python.lang.compatibility.python37.python37-compatibility-importlib2)
        ;;
      frontend) packs+=(--config p/typescript --config p/react) ;;
    esac
    # No --error: findings are reported, the gate (#36) decides. Rule packs come from the Semgrep
    # registry (public packs, no account); metrics and the version check are off.
    docker_run "$SEMGREP_IMAGE" semgrep scan --metrics off --disable-version-check --quiet \
      "${packs[@]}" \
      --json-output "$REPORTS/sast/semgrep-$component.json" \
      --sarif-output "$REPORTS/sast/semgrep-$component.sarif" \
      "$component"
    count="$(stats semgrep "$REPORTS/sast/semgrep-$component.json")"
    total=$((total + count))
    echo "semgrep $component: $count findings"
    summary "| $component | $count |"
  done
  output findings "$total"
}

sca() {
  mkdir -p "$REPORTS/sca"
  local component total=0 count all
  summary "| Component | Vulnerabilities (all) | HIGH or CRITICAL |"
  summary "| --- | --- | --- |"
  for component in "${COMPONENTS[@]}"; do
    # Full report with every severity; the gate counts HIGH and CRITICAL only (brief §3e).
    docker_run "$TRIVY_IMAGE" fs --scanners vuln --no-progress --skip-version-check \
      --ignorefile .trivyignore --exit-code 0 \
      --format json --output "$REPORTS/sca/trivy-fs-$component.json" "$component"
    docker_run "$TRIVY_IMAGE" convert --format sarif \
      --output "$REPORTS/sca/trivy-fs-$component.sarif" "$REPORTS/sca/trivy-fs-$component.json"
    all="$(stats trivy-all "$REPORTS/sca/trivy-fs-$component.json")"
    count="$(stats trivy "$REPORTS/sca/trivy-fs-$component.json")"
    total=$((total + count))
    echo "trivy fs $component: $all vulnerabilities, $count HIGH or CRITICAL"
    summary "| $component | $all | $count |"
  done
  output findings "$total"
}

secrets() {
  mkdir -p "$REPORTS/secrets"
  # All refs of the full history (the pipeline checks out with fetch-depth 0). Secret values are
  # redacted in the report, so the evidence never contains them.
  docker_run "$GITLEAKS_IMAGE" git --no-banner --redact --exit-code 0 \
    --config /src/.gitleaks.toml --log-opts="--all" \
    --report-format json --report-path "/src/$REPORTS/secrets/gitleaks.json" /src
  docker_run "$GITLEAKS_IMAGE" git --no-banner --redact --exit-code 0 \
    --config /src/.gitleaks.toml --log-opts="--all" \
    --report-format sarif --report-path "/src/$REPORTS/secrets/gitleaks.sarif" /src
  local count
  count="$(stats gitleaks "$REPORTS/secrets/gitleaks.json")"
  echo "gitleaks: $count findings"
  summary "| Gitleaks findings | $count |"
  summary "| --- | --- |"
  output findings "$count"
}

case "${1:-}" in
  sbom | sast | sca | secrets) "$1" ;;
  *)
    echo "usage: $0 sbom|sast|sca|secrets" >&2
    exit 2
    ;;
esac
