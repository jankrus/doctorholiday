-- Database objects the tables depend on (docs/architecture/database.md).
-- citext and btree_gist are trusted extensions, so the non-superuser owner role can create them.

CREATE EXTENSION citext;
CREATE EXTENSION btree_gist;

-- Case-insensitive e-mail that rejects obviously malformed values; the full check is in the API.
CREATE DOMAIN email_address AS citext
  CHECK (length(VALUE) <= 254 AND VALUE ~ '^[^@\s]+@[^@\s]+$');

-- Local time ranges for the working_hours exclusion constraint (BR-08).
CREATE TYPE timerange AS RANGE (subtype = time);
