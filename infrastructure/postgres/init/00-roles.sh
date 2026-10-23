#!/bin/sh
# Runs once, on the first start with an empty data volume, as the bootstrap superuser.
# Creates the database, the owner role that runs the migrations and the application role.
# Tables and grants come from the migrations (backend/migrations), not from here.
set -eu

for name in db_owner_password db_app_password; do
  secret="/run/secrets/$name"
  if [ "$(tr -d '\n' < "$secret" | wc -c)" -lt 16 ]; then
    echo "init: secret $name is missing or shorter than 16 characters" >&2
    exit 1
  fi
done

# Passwords are read inside psql (\set with backticks) and quoted with :'var', so they
# never appear in a process list or get spliced into SQL unquoted.
psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\set owner_password `cat /run/secrets/db_owner_password`
\set app_password `cat /run/secrets/db_app_password`

CREATE ROLE doctorholiday_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'owner_password';
CREATE ROLE doctorholiday_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'app_password';
\unset owner_password
\unset app_password

CREATE DATABASE doctorholiday OWNER doctorholiday_owner ENCODING 'UTF8';
ALTER DATABASE doctorholiday SET timezone TO 'UTC';
REVOKE ALL ON DATABASE doctorholiday FROM PUBLIC;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
GRANT CONNECT ON DATABASE doctorholiday TO doctorholiday_app;

\connect doctorholiday
-- public is owned by pg_database_owner, i.e. doctorholiday_owner; the app may only use it
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO doctorholiday_app;
SQL
