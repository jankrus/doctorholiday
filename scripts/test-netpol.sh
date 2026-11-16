#!/usr/bin/env bash
# Proves that the NetworkPolicies are enforced (issue #41, brief §4d). Run by `make verify` against
# a running cluster; every line says PASS or FAIL, the exit code is 1 if any check failed. The
# output is also written to reports/netpol/ (git-ignored), the evidence job copies it later (#44).
#
#   scripts/test-netpol.sh [kube-context] [namespace]
#
# Negative checks (must be BLOCKED):
#   1. a throwaway pod in the namespace cannot reach postgres:5432
#   2. the frontend cannot reach postgres:5432
#   3. the backend cannot reach the internet (example.com:443)
# Controls: `nc` exists and can connect to a listening port, so "blocked" is not a missing tool.
# Positive checks (must WORK, otherwise a blocked connection above proves nothing):
#   4. the backend reaches postgres:5432
#   5. the backend resolves names (DNS egress is allowed)
#   6. the frontend and the backend answer through the ingress
#
# The throwaway pod uses the frontend image that is already on the node (it contains busybox
# `nc`), so no image is pulled, and it complies with Pod Security `restricted`.
set -uo pipefail

context="${1:-kind-doctorholiday}"
namespace="${2:-doctorholiday}"
kubectl=(kubectl --context "$context" --namespace "$namespace")
probe=netpol-probe
failures=0

reports_dir="reports/netpol"
mkdir -p "$reports_dir"
report="$reports_dir/test-netpol-$(date -u +%Y%m%dT%H%M%SZ).txt"
exec > >(tee "$report") 2>&1

pass() { echo "PASS  $1"; }
fail() {
  echo "FAIL  $1"
  failures=$((failures + 1))
}

cleanup() { "${kubectl[@]}" delete pod "$probe" --ignore-not-found --wait=false > /dev/null 2>&1; }
trap cleanup EXIT

echo "NetworkPolicy check, context $context, namespace $namespace, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"${kubectl[@]}" get networkpolicy --no-headers -o custom-columns=NAME:.metadata.name | sed 's/^/policy /'

frontend_image="$("${kubectl[@]}" get deployment frontend -o 'jsonpath={.spec.template.spec.containers[0].image}')"

cleanup
"${kubectl[@]}" apply -f - > /dev/null << EOF
apiVersion: v1
kind: Pod
metadata:
  name: $probe
  labels:
    app.kubernetes.io/name: $probe
spec:
  automountServiceAccountToken: false
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: probe
      image: $frontend_image
      imagePullPolicy: IfNotPresent
      command: ["sleep", "300"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
EOF
"${kubectl[@]}" wait --for=condition=Ready "pod/$probe" --timeout=120s > /dev/null || {
  fail "the throwaway pod did not become ready"
  exit 1
}

# `nc -z -w 3 host port` exits 0 when the connection is made.
blocked_from_probe() { ! "${kubectl[@]}" exec "$probe" -- nc -z -w 3 "$1" "$2" > /dev/null 2>&1; }
blocked_from_frontend() { ! "${kubectl[@]}" exec deploy/frontend -- nc -z -w 3 "$1" "$2" > /dev/null 2>&1; }
python_connect() { # host port: exit 0 if a TCP connection can be made from the backend pod
  "${kubectl[@]}" exec deploy/backend -- python -c \
    'import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 3).close()' "$1" "$2" > /dev/null 2>&1
}

echo
echo "--- controls (a blocked connection only proves something if the tool works)"
"${kubectl[@]}" exec "$probe" -- sh -c 'command -v nc' > /dev/null 2>&1 \
  && pass "nc exists in the throwaway pod" || fail "nc is missing in the throwaway pod"
"${kubectl[@]}" exec deploy/frontend -- nc -z -w 3 127.0.0.1 8080 > /dev/null 2>&1 \
  && pass "nc connects to a listening port (frontend -> 127.0.0.1:8080)" || fail "nc cannot connect to a listening port"

echo
echo "--- must be blocked"
blocked_from_probe postgres 5432 && pass "throwaway pod -> postgres:5432 is blocked" \
  || fail "throwaway pod reached postgres:5432"
blocked_from_frontend postgres 5432 && pass "frontend -> postgres:5432 is blocked" \
  || fail "frontend reached postgres:5432"
python_connect example.com 443 && fail "backend reached example.com:443 (internet)" \
  || pass "backend -> example.com:443 is blocked"

echo
echo "--- must work"
python_connect postgres 5432 && pass "backend -> postgres:5432 works" \
  || fail "backend cannot reach postgres:5432"
"${kubectl[@]}" exec deploy/backend -- python -c \
  'import socket; socket.getaddrinfo("postgres", 5432)' > /dev/null 2>&1 \
  && pass "backend resolves names through kube-dns" || fail "backend cannot resolve names"
status="$(curl --silent --insecure --output /dev/null --write-out '%{http_code}' --max-time 10 https://doctorholiday.localhost/ || true)"
[[ "$status" == "200" ]] && pass "https://doctorholiday.localhost/ answers 200 through the ingress" \
  || fail "https://doctorholiday.localhost/ answered '$status'"
# No session: the backend answers 401 UNAUTHENTICATED, so the request reached it through the ingress.
status="$(curl --silent --insecure --output /dev/null --write-out '%{http_code}' --max-time 10 https://doctorholiday.localhost/api/v1/auth/me || true)"
[[ "$status" == "401" ]] && pass "https://doctorholiday.localhost/api/v1/auth/me reaches the backend (401 without a session)" \
  || fail "https://doctorholiday.localhost/api/v1/auth/me answered '$status' instead of 401"

echo
if ((failures > 0)); then
  echo "$failures check(s) failed. Report: $report"
  exit 1
fi
echo "All checks passed. Report: $report"
