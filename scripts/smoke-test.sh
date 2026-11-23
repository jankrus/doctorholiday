#!/usr/bin/env bash
# Smoke test of the deployed application through the ingress (issue #43). Every line says PASS or
# FAIL; the exit code is 1 if any check failed. The output is also written to
# reports/smoke/ (git-ignored), the `deploy` job uploads it as evidence.
#
#   scripts/smoke-test.sh [base-url]        default: https://doctorholiday.localhost
#
# What is checked (only HTTP, the same way a browser reaches the app):
#   1. the frontend answers on /, and an API call without a session is refused (401)
#   2. a cross-site write is refused by the CSRF check (403) and the API answers over HTTPS with HSTS
#   3. a first account registers and logs in; on a fresh cluster (EXPECT_FIRST_ADMIN=1, set by the
#      pipeline) it must have become ADMIN (#15)
#   4. a second account registers and logs in as PATIENT and can read doctors and its own appointments
#   5. the patient cannot reach admin data, and logout ends the session
#
# Not checked: setting a doctor's working hours and booking an appointment. Doctor accounts only
# exist through invitations and role changes (#55, #18), which are not implemented yet; the booking
# flow is covered by the database tests of the backend (docs/report/deviations.md, D-11).
#
# Environment: EXPECT_FIRST_ADMIN=1 asserts the ADMIN role of the first account; CURL_OPTS adds curl
# options. The self-signed certificate of the cluster is accepted (-k) on purpose.
set -uo pipefail

base="${1:-https://doctorholiday.localhost}"
host="${base#*://}"
host="${host%%/*}"
port=443
[[ "$base" == http://* ]] && port=80
reports_dir="reports/smoke"
mkdir -p "$reports_dir"
report="$reports_dir/smoke-test-$(date -u +%Y%m%dT%H%M%SZ).txt"
exec > >(tee "$report") 2>&1

if command -v python3 > /dev/null 2>&1 && python3 -c 'pass' > /dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

failures=0
pass() { echo "PASS  $1"; }
fail() {
  echo "FAIL  $1"
  failures=$((failures + 1))
}
check() { # check <description> <expected status> <actual status>
  if [[ "$3" == "$2" ]]; then pass "$1 ($3)"; else fail "$1: expected $2, got $3"; fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# A throwaway password per run, never printed. Long and random, so the common-password check passes.
secret="Smoke-$(openssl rand -hex 12)-Pw"
suffix="$(openssl rand -hex 4)"
admin_email="smoke-admin-$suffix@example.com"
patient_email="smoke-patient-$suffix@example.com"

# api <jar> <method> <path> [json body]: prints the status code, the body goes to $tmp/body.
api() {
  local jar="$1" method="$2" path="$3" data="${4:-}"
  local args=(--silent --insecure --max-time 20 --resolve "$host:$port:127.0.0.1"
    --cookie "$tmp/$jar" --cookie-jar "$tmp/$jar" --output "$tmp/body" --dump-header "$tmp/headers"
    --write-out '%{http_code}' --request "$method")
  if [[ -n "$data" ]]; then args+=(--header 'Content-Type: application/json' --data "$data"); fi
  # shellcheck disable=SC2086
  curl "${args[@]}" ${CURL_OPTS:-} "$base$path"
}

json_field() { # json_field <dotted path>: read from $tmp/body
  "$PYTHON" -c '
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
print(value)' "$tmp/body" "$1" 2> /dev/null
}

echo "Smoke test against $base"

# The ingress may need a moment to route to a pod that just became Ready: wait until the API answers
# at all (401 without a session) before the checks start.
for _ in $(seq 1 30); do
  if [[ "$(api anon GET /api/v1/auth/me)" == 401 ]]; then break; fi
  sleep 2
done

# 1. frontend and unauthenticated API
status="$(api anon GET /)"
check "frontend answers on /" 200 "$status"
if grep -q -i '<div id="root"' "$tmp/body"; then pass "frontend serves the single-page app"; else fail "frontend body has no app root"; fi
status="$(api anon GET /api/v1/auth/me)"
check "API refuses a request without a session" 401 "$status"
if grep -q -i '^strict-transport-security:' "$tmp/headers"; then pass "HSTS header on the API response"; else fail "no Strict-Transport-Security header"; fi

# 2. CSRF check of the backend (#19)
status="$(CURL_OPTS="--header Origin:https://evil.example.org" api anon POST /api/v1/auth/logout)"
check "cross-site write is refused" 403 "$status"

# 3. first account
status="$(api admin POST /api/v1/auth/register "{\"email\":\"$admin_email\",\"password\":\"$secret\",\"displayName\":\"Smoke Admin\"}")"
if [[ "$status" == 2?? ]]; then pass "first account registers ($status)"; else fail "registration: got $status"; fi
status="$(api admin POST /api/v1/auth/login "{\"email\":\"$admin_email\",\"password\":\"$secret\"}")"
check "first account logs in" 200 "$status"
status="$(api admin GET /api/v1/auth/me)"
check "session is valid" 200 "$status"
role="$(json_field user.role)"
if [[ "${EXPECT_FIRST_ADMIN:-0}" == "1" ]]; then
  if [[ "$role" == "ADMIN" ]]; then pass "first login on a fresh system became ADMIN"; else fail "first account has role '$role', expected ADMIN"; fi
else
  echo "INFO  first account has role '$role' (EXPECT_FIRST_ADMIN is not set)"
fi

# 4. patient
status="$(api patient POST /api/v1/auth/register "{\"email\":\"$patient_email\",\"password\":\"$secret\"}")"
if [[ "$status" == 2?? ]]; then pass "second account registers ($status)"; else fail "registration: got $status"; fi
status="$(api patient POST /api/v1/auth/login "{\"email\":\"$patient_email\",\"password\":\"$secret\"}")"
check "second account logs in" 200 "$status"
status="$(api patient GET /api/v1/auth/me)"
check "patient session is valid" 200 "$status"
role="$(json_field user.role)"
if [[ "$role" == "PATIENT" ]]; then pass "second account is PATIENT"; else fail "second account has role '$role'"; fi
status="$(api patient GET /api/v1/doctors)"
check "patient lists doctors" 200 "$status"
status="$(api patient GET /api/v1/appointments/me)"
check "patient lists its own appointments" 200 "$status"

# 5. authorisation and logout
status="$(api patient GET /api/v1/audit-events)"
if [[ "$status" == 403 || "$status" == 404 ]]; then pass "patient cannot read the audit log ($status)"; else fail "audit log answered $status to a patient"; fi
status="$(api patient POST /api/v1/auth/logout)"
check "logout" 204 "$status"
status="$(api patient GET /api/v1/auth/me)"
check "session is gone after logout" 401 "$status"

echo
if [[ $failures -eq 0 ]]; then
  echo "Smoke test passed."
else
  echo "Smoke test: $failures check(s) failed."
  exit 1
fi
