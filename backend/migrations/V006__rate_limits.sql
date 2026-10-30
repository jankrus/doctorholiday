-- Generalises the failed-login counters of V005 to every rate limit of BR-03 (#14): registration,
-- MFA verification, invitation acceptance, password reset and re-authentication besides login.
-- The scope names the endpoint and what is counted; `attempts` counts whatever that endpoint's
-- limit counts (failures for login, every request for registration).

ALTER TABLE login_throttles RENAME TO rate_limits;
ALTER TABLE rate_limits RENAME COLUMN failures TO attempts;
ALTER TABLE rate_limits RENAME CONSTRAINT login_throttles_pkey TO rate_limits_pkey;
ALTER TABLE rate_limits RENAME CONSTRAINT login_throttles_key_hash_check TO rate_limits_key_hash_check;
ALTER TABLE rate_limits RENAME CONSTRAINT login_throttles_failures_check TO rate_limits_attempts_check;

ALTER TABLE rate_limits DROP CONSTRAINT login_throttles_scope_check;
UPDATE rate_limits SET scope = 'LOGIN_' || scope;
-- All scopes of BR-03 up front, like the audit actions in V002; the endpoints follow in their tickets.
ALTER TABLE rate_limits ADD CONSTRAINT rate_limits_scope_check CHECK (scope IN (
  'LOGIN_IP', 'LOGIN_ACCOUNT', 'REGISTRATION_IP', 'MFA_VERIFICATION_USER',
  'INVITATION_ACCEPTANCE_IP', 'PASSWORD_RESET_IP', 'REAUTHENTICATION_USER'
));

-- The cleanup deletes expired rows per scope, because every scope has its own window.
DROP INDEX login_throttles_window_started_at_idx;
CREATE INDEX rate_limits_scope_window_started_at_idx ON rate_limits (scope, window_started_at);

-- Grants follow the table through the rename (V005).
