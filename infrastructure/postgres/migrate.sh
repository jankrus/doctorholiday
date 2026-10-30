#!/bin/sh
# Applies backend/migrations/V<nnn>__<name>.sql in order, each exactly once, as the schema owner.
# Every file runs in its own transaction together with its row in schema_migrations, so a failing
# migration leaves no trace. A migration that was changed after it was applied stops the run.
# Connection settings come from the libpq variables PGHOST, PGDATABASE, PGUSER and PGPASSWORD_FILE.
set -eu

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/migrations}"
: "${PGHOST:?}" "${PGDATABASE:?}" "${PGUSER:?}" "${PGPASSWORD_FILE:?}"
PGPASSWORD="$(cat "$PGPASSWORD_FILE")"
export PGPASSWORD

run_psql() {
  psql --no-psqlrc --quiet --set ON_ERROR_STOP=1 "$@"
}

run_psql <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    text PRIMARY KEY,
  checksum   text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

applied=0
for file in "$MIGRATIONS_DIR"/V*.sql; do
  if [ ! -e "$file" ]; then
    echo "migrate: no migrations found in $MIGRATIONS_DIR" >&2
    exit 1
  fi
  version="$(basename "$file" .sql)"
  case "$version" in
    *[!A-Za-z0-9_]*) echo "migrate: invalid file name $file" >&2; exit 1 ;;
    V[0-9][0-9][0-9]__?*) ;;
    *) echo "migrate: invalid file name $file" >&2; exit 1 ;;
  esac
  checksum="$(sha256sum "$file" | cut -d ' ' -f 1)"

  recorded="$(echo "SELECT checksum FROM schema_migrations WHERE version = :'version';" |
    run_psql --tuples-only --no-align --set version="$version")"
  if [ "$recorded" = "$checksum" ]; then
    continue
  elif [ -n "$recorded" ]; then
    echo "migrate: $version was changed after it was applied; add a new migration instead" >&2
    exit 1
  fi

  echo "migrate: applying $version"
  {
    echo "SELECT pg_advisory_xact_lock(hashtext('schema_migrations'));"
    cat "$file"
    echo
    echo "INSERT INTO schema_migrations (version, checksum) VALUES (:'version', :'checksum');"
  } | run_psql --single-transaction --file=- --output=/dev/null --set version="$version" --set checksum="$checksum"
  applied=$((applied + 1))
done

echo "migrate: database is up to date ($applied applied)"
