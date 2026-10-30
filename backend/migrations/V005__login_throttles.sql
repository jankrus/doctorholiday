-- Failed-login counters for rate limiting and temporary lockout (#14, BR-03).
-- One row per client IP and per e-mail address that failed to log in recently. Keyed by the
-- SHA-256 of the IP or e-mail, so neither is stored in clear; unknown e-mails get a counter too,
-- so a lockout does not reveal whether an account exists. Rows are short-lived: the backend
-- deletes them once their window and lockout are over, and the account row after a login.

CREATE TABLE login_throttles (
  scope             text NOT NULL CHECK (scope IN ('IP', 'ACCOUNT')),
  key_hash          bytea NOT NULL CHECK (octet_length(key_hash) = 32),
  window_started_at timestamptz NOT NULL DEFAULT now(),
  failures          smallint NOT NULL DEFAULT 0 CHECK (failures >= 0),
  locked_until      timestamptz,
  PRIMARY KEY (scope, key_hash)
);
CREATE INDEX login_throttles_window_started_at_idx ON login_throttles (window_started_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON login_throttles TO doctorholiday_app;
