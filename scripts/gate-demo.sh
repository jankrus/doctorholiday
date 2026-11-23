#!/usr/bin/env bash
# Demonstration of the quality gate (issue #36): puts one fault into a throw-away checkout, runs the
# real scans and the real gate on it and checks that the gate blocks for exactly that reason. Used
# by the workflow `gate-demo.yml`; nothing is committed, pushed or signed, the fault lives only in
# the checkout of the run.
#
#   scripts/gate-demo.sh prepare  <scenario>   before the scans: put the fault in
#   scripts/gate-demo.sh finalize <scenario>   after the scans, before the gate (last changes)
#   scripts/gate-demo.sh assert   <scenario>   after the gate: it must have blocked for that reason
#
# Scenarios
#   clean          no fault; the gate must pass (control: the failures below come from the faults)
#   secret         a token-shaped string, made up at random, in a file of a local commit (Gitleaks)
#   vulnerability  a requirements.txt with a PyYAML that has a CRITICAL vulnerability (Trivy)
#   unsigned       the backend reference is an image that is not signed with our key (cosign)
#
# `prepare` also takes the digests of the latest signed images from the `evidence` branch (checked
# out by the workflow at $EVIDENCE_SRC, default `evidence-src`) into reports/images/<c>/.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
phase="${1:-}"
scenario="${2:-}"
case "$scenario" in
  clean | secret | vulnerability | unsigned) ;;
  *)
    echo "usage: $0 prepare|finalize|assert clean|secret|vulnerability|unsigned" >&2
    exit 2
    ;;
esac

reports="${REPORTS_DIR:-reports}"
evidence_src="${EVIDENCE_SRC:-evidence-src}"
# An image of a public registry that our key never signed (pinned digest).
UNSIGNED_REF="docker.io/library/alpine@sha256:a8560b36e8b8210634f77d9f7f9efd7ffa463e380b75e2e74aff4511df3ef88c"

if command -v python3 > /dev/null 2>&1 && python3 -c 'pass' > /dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

prepare() {
  local component latest
  for component in backend frontend; do
    latest="$(find "$evidence_src/evidence/$component/run" -name '*-image-ref.txt' 2> /dev/null | sort | tail -1)"
    [[ -n "$latest" ]] || { echo "no image reference of $component on the evidence branch" >&2; exit 1; }
    mkdir -p "$reports/images/$component"
    cp "$latest" "$reports/images/$component/image-ref.txt"
    echo "$component: $(tr -d '[:space:]' < "$reports/images/$component/image-ref.txt") (from $(basename "$latest"))"
  done
  case "$scenario" in
    secret)
      # Random, so the repository never contains it, and in the shape of a GitHub token so that the
      # default Gitleaks rules match. It is committed locally only, so the history scan sees it.
      printf 'GITHUB_TOKEN = "ghp_%s"\n' "$(openssl rand -hex 18)" > backend/demo_leaked_token.py
      git add backend/demo_leaked_token.py
      git -c user.name=gate-demo -c user.email=gate-demo@example.invalid commit --quiet \
        --message "gate demo: a leaked token (local commit, never pushed)"
      echo "secret: a token-shaped string is in the history of this checkout"
      ;;
    vulnerability)
      printf 'pyyaml==5.3\n' > backend/requirements.txt
      echo "vulnerability: backend/requirements.txt pins pyyaml 5.3 (CVE-2020-14343, CRITICAL)"
      ;;
  esac
}

finalize() {
  if [[ "$scenario" == "unsigned" ]]; then
    # After the image scans, so that only the signature check sees the unsigned image.
    echo "$UNSIGNED_REF" > "$reports/images/backend/image-ref.txt"
    echo "unsigned: backend now refers to $UNSIGNED_REF"
  fi
}

assert_result() {
  local file="$reports/gate/quality-gate.json" expected
  case "$scenario" in
    clean) expected="" ;;
    secret) expected="secrets" ;;
    vulnerability) expected="vulnerabilities" ;;
    unsigned) expected="signatures" ;;
  esac
  [[ -s "$file" ]] || { echo "no gate report at $file" >&2; exit 1; }
  "$PYTHON" - "$file" "$scenario" "$expected" << 'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
scenario, expected = sys.argv[2], sys.argv[3]
failed = sorted(rule["rule"] for rule in report["rules"] if not rule["passed"])
want = [expected] if expected else []
if failed != want:
    print(f"gate demo '{scenario}': rules that blocked: {failed}, expected: {want}", file=sys.stderr)
    sys.exit(1)
if want:
    print(f"gate demo '{scenario}': blocked as expected by rule '{expected}'")
else:
    print("gate demo 'clean': the gate passed as expected")
PY
}

case "$phase" in
  prepare) prepare ;;
  finalize) finalize ;;
  assert) assert_result ;;
  *)
    echo "usage: $0 prepare|finalize|assert <scenario>" >&2
    exit 2
    ;;
esac
