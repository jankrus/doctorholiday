#!/usr/bin/env bash
# Creates the secrets of the cluster at deploy time (issues #30, #39, #40, #42; SR-05).
#
#   scripts/k8s-secrets.sh <kube-context> <namespace>
#
# Secrets in this project are never committed. This script generates them with `openssl rand` and
# creates the Kubernetes Secrets:
#
#   db-credentials     db_superuser_password, db_owner_password, db_app_password   (postgres pod,
#                      the migration job gets only the owner password)
#   backend-secrets    DATABASE_URL (with the application role's password), MFA_ENCRYPTION_KEY
#                      (32 random bytes, base64url with padding, the format config.py validates),
#                      SESSION_SECRET (at least 32 characters, see #59)
#   doctorholiday-tls  self-signed certificate and key for doctorholiday.localhost (ingress)
#
# Idempotent and never destructive: a Secret that already exists is left alone, so `make up` can
# run twice and a rotated password is never overwritten by accident. To rotate, delete the Secret
# (and for the database: `make down`, the password lives in the volume) and run `make secrets`.
#
# Values never appear in the output, in the process list or in the repository: they are written to
# files in a private temporary directory (mode 700) that is deleted when the script ends.
set -euo pipefail
umask 077
export MSYS_NO_PATHCONV=1 # Git Bash on Windows must not rewrite the "/CN=..." argument of openssl

context="${1:?usage: $0 <kube-context> <namespace>}"
namespace="${2:?usage: $0 <kube-context> <namespace>}"
kubectl=(kubectl --context "$context" --namespace "$namespace")

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

exists() { "${kubectl[@]}" get secret "$1" > /dev/null 2>&1; }

if exists db-credentials; then
  echo "secret db-credentials exists, left unchanged"
else
  for name in db_superuser_password db_owner_password db_app_password; do
    openssl rand -hex 32 > "$tmp/$name" # 64 hex characters, no padding or special characters
  done
  "${kubectl[@]}" create secret generic db-credentials \
    --from-file="db_superuser_password=$tmp/db_superuser_password" \
    --from-file="db_owner_password=$tmp/db_owner_password" \
    --from-file="db_app_password=$tmp/db_app_password" > /dev/null
  echo "secret db-credentials created"
fi

if exists backend-secrets; then
  echo "secret backend-secrets exists, left unchanged"
else
  # The application role's password comes from the cluster, so the URL always matches the database.
  app_password="$("${kubectl[@]}" get secret db-credentials -o 'jsonpath={.data.db_app_password}' | base64 --decode)"
  printf 'postgresql+psycopg://doctorholiday_app:%s@postgres:5432/doctorholiday' "$app_password" > "$tmp/DATABASE_URL"
  openssl rand 32 | openssl base64 -A | tr '+/' '-_' > "$tmp/MFA_ENCRYPTION_KEY"
  openssl rand -base64 32 | tr -d '\n' > "$tmp/SESSION_SECRET"
  "${kubectl[@]}" create secret generic backend-secrets \
    --from-file="DATABASE_URL=$tmp/DATABASE_URL" \
    --from-file="MFA_ENCRYPTION_KEY=$tmp/MFA_ENCRYPTION_KEY" \
    --from-file="SESSION_SECRET=$tmp/SESSION_SECRET" > /dev/null
  echo "secret backend-secrets created"
fi

if exists doctorholiday-tls; then
  echo "secret doctorholiday-tls exists, left unchanged"
else
  openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 \
    -keyout "$tmp/tls.key" -out "$tmp/tls.crt" \
    -subj "/CN=doctorholiday.localhost" \
    -addext "subjectAltName=DNS:doctorholiday.localhost" 2> /dev/null
  "${kubectl[@]}" create secret tls doctorholiday-tls --cert="$tmp/tls.crt" --key="$tmp/tls.key" > /dev/null
  echo "secret doctorholiday-tls created (self-signed, valid 365 days)"
fi

for secret in db-credentials backend-secrets doctorholiday-tls; do
  "${kubectl[@]}" label secret "$secret" app.kubernetes.io/part-of=doctorholiday --overwrite > /dev/null
done
