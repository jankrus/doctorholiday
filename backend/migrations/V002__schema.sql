-- Tables, constraints and indexes of the physical ER model
-- (docs/architecture/database.md, docs/architecture/database-erm.drawio).
-- Every FK references users(id). Rows that only exist for a user's login cascade; every other FK
-- keeps NO ACTION, so history never loses its references. Users are never hard-deleted (BR-13).

CREATE TABLE users (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email                 email_address UNIQUE,
  display_name          text CHECK (char_length(display_name) BETWEEN 1 AND 100),
  role                  text NOT NULL CHECK (role IN ('PATIENT', 'STAFF', 'DOCTOR', 'ADMIN')),
  is_active             boolean NOT NULL DEFAULT true,
  created_at            timestamptz NOT NULL DEFAULT now(),
  deleted_at            timestamptz,
  mfa_offer_declined_at timestamptz,
  -- the e-mail is erased by account deletion and only then
  CONSTRAINT users_email_deleted_check CHECK ((deleted_at IS NULL) = (email IS NOT NULL)),
  CONSTRAINT users_deleted_inactive_check CHECK (deleted_at IS NULL OR NOT is_active),
  CONSTRAINT users_mfa_offer_patient_check CHECK (mfa_offer_declined_at IS NULL OR role = 'PATIENT')
);
CREATE INDEX users_role_idx ON users (role);
CREATE INDEX users_created_at_idx ON users (created_at);

-- Only the auth module reads this table.
CREATE TABLE credentials (
  user_id             uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
  password_hash       text NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
  mfa_secret_enc      bytea,
  mfa_enabled         boolean NOT NULL DEFAULT false,
  -- RFC 6238 §5.2: time step of the last accepted TOTP code, so a code is never accepted twice
  totp_last_step      bigint,
  password_changed_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT credentials_mfa_secret_check CHECK (NOT mfa_enabled OR mfa_secret_enc IS NOT NULL)
);

CREATE TABLE sessions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash   bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  user_id      uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  state        text NOT NULL CHECK (state IN ('MFA_PENDING', 'MFA_ENROLLMENT_REQUIRED', 'ACTIVE')),
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  CONSTRAINT sessions_expiry_check CHECK (expires_at > created_at)
);
CREATE INDEX sessions_user_id_idx ON sessions (user_id);
CREATE INDEX sessions_expires_at_idx ON sessions (expires_at);

CREATE TABLE recovery_codes (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  code_hash  text NOT NULL,
  used_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX recovery_codes_user_id_idx ON recovery_codes (user_id);

CREATE TABLE password_reset_codes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  code_hash       text NOT NULL,
  issued_by_id    uuid NOT NULL REFERENCES users (id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,
  used_at         timestamptz,
  failed_attempts smallint NOT NULL DEFAULT 0 CHECK (failed_attempts BETWEEN 0 AND 5),
  CONSTRAINT password_reset_codes_expiry_check CHECK (expires_at = created_at + interval '15 minutes')
);
-- at most one open code per user (BR-25)
CREATE UNIQUE INDEX password_reset_codes_open_user_id_key ON password_reset_codes (user_id) WHERE used_at IS NULL;

CREATE TABLE invitations (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         email_address NOT NULL,
  role          text NOT NULL CHECK (role IN ('STAFF', 'DOCTOR', 'ADMIN')),
  display_name  text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 100),
  token_hash    bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
  invited_by_id uuid NOT NULL REFERENCES users (id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,
  accepted_at   timestamptz,
  user_id       uuid UNIQUE REFERENCES users (id),
  CONSTRAINT invitations_expiry_check CHECK (expires_at = created_at + interval '72 hours'),
  CONSTRAINT invitations_accepted_check CHECK ((accepted_at IS NULL) = (user_id IS NULL))
);
CREATE INDEX invitations_email_idx ON invitations (email);

-- Single row, created by V003 (BR-18).
CREATE TABLE practice_settings (
  id                          smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  practice_name               text NOT NULL CHECK (char_length(practice_name) BETWEEN 1 AND 100),
  cancellation_deadline_hours integer NOT NULL DEFAULT 24 CHECK (cancellation_deadline_hours BETWEEN 0 AND 168),
  appointment_minutes         integer NOT NULL DEFAULT 15 CHECK (appointment_minutes BETWEEN 5 AND 240),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  -- NULL means the practice setup is still pending
  updated_by_id               uuid REFERENCES users (id)
);

-- Single row, created by V003; locked with SELECT ... FOR UPDATE at login (BR-04).
CREATE TABLE admin_bootstrap (
  id              smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  bootstrapped    boolean NOT NULL DEFAULT false,
  admin_id        uuid REFERENCES users (id),
  bootstrapped_at timestamptz,
  CONSTRAINT admin_bootstrap_admin_check CHECK (bootstrapped = (admin_id IS NOT NULL)),
  CONSTRAINT admin_bootstrap_timestamp_check CHECK ((admin_id IS NULL) = (bootstrapped_at IS NULL))
);

CREATE TABLE admin_access_grants (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id         uuid NOT NULL REFERENCES users (id),
  purpose          text NOT NULL
    CHECK (purpose IN ('SUPPORT_REQUEST', 'INCIDENT_RESPONSE', 'DATA_SUBJECT_REQUEST', 'AUDIT')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz NOT NULL,
  -- set once the APPOINTMENT_ACCESS_EXPIRED audit event is written, so it is written exactly once
  expiry_logged_at timestamptz,
  CONSTRAINT admin_access_grants_expiry_check CHECK (expires_at = created_at + interval '30 minutes'),
  -- BR-17: one active grant per admin, even for concurrent requests
  CONSTRAINT admin_access_grants_no_overlap
    EXCLUDE USING gist (admin_id WITH =, tstzrange(created_at, expires_at) WITH &&)
);
CREATE INDEX admin_access_grants_expiry_unlogged_idx ON admin_access_grants (expires_at)
  WHERE expiry_logged_at IS NULL;

-- Local time in Europe/Berlin (BR-08).
CREATE TABLE working_hours (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doctor_id     uuid NOT NULL REFERENCES users (id),
  weekday       smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7), -- ISO, 1 = Monday
  start_time    time NOT NULL,
  end_time      time NOT NULL,
  updated_by_id uuid NOT NULL REFERENCES users (id),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT working_hours_range_check CHECK (end_time > start_time),
  CONSTRAINT working_hours_granularity_check
    CHECK (extract(epoch FROM start_time) % 300 = 0 AND extract(epoch FROM end_time) % 300 = 0),
  -- BR-08: entries of one weekday do not overlap, even for concurrent requests
  CONSTRAINT working_hours_no_overlap
    EXCLUDE USING gist (doctor_id WITH =, weekday WITH =, timerange(start_time, end_time) WITH &&)
);

CREATE TABLE absences (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doctor_id     uuid NOT NULL REFERENCES users (id),
  starts_at     timestamptz NOT NULL,
  ends_at       timestamptz NOT NULL,
  created_by_id uuid NOT NULL REFERENCES users (id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT absences_range_check CHECK (ends_at > starts_at),
  CONSTRAINT absences_duration_check CHECK (ends_at - starts_at <= interval '90 days'),
  CONSTRAINT absences_granularity_check
    CHECK (extract(epoch FROM starts_at) % 60 = 0 AND extract(epoch FROM ends_at) % 60 = 0)
);
CREATE INDEX absences_doctor_id_ends_at_idx ON absences (doctor_id, ends_at);

-- Never deleted (BR-11).
CREATE TABLE appointments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doctor_id       uuid NOT NULL REFERENCES users (id),
  starts_at       timestamptz NOT NULL,
  ends_at         timestamptz NOT NULL,
  patient_id      uuid REFERENCES users (id),
  guest_name      text CHECK (char_length(guest_name) BETWEEN 1 AND 100),
  guest_phone     text CHECK (guest_phone ~ '^\+[1-9][0-9]{1,14}$'), -- E.164
  guest_erased_at timestamptz,
  booked_by_id    uuid NOT NULL REFERENCES users (id),
  reason          text NOT NULL CHECK (reason IN (
    'CHECKUP', 'FOLLOW_UP', 'VACCINATION', 'PRESCRIPTION', 'CONSULTATION',
    'BLOOD_TEST', 'BLOOD_TEST_FASTING', 'OTHER'
  )),
  status          text NOT NULL DEFAULT 'BOOKED' CHECK (status IN ('BOOKED', 'CANCELLED')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  cancelled_at    timestamptz,
  cancelled_by_id uuid REFERENCES users (id),
  CONSTRAINT appointments_range_check CHECK (ends_at > starts_at),
  CONSTRAINT appointments_cancellation_check CHECK (
    (status = 'BOOKED' AND cancelled_at IS NULL AND cancelled_by_id IS NULL)
    OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL AND cancelled_by_id IS NOT NULL)
  ),
  -- exactly one of: patient, guest, guest erased by the cleanup job (BR-24)
  CONSTRAINT appointments_party_check CHECK (
    (patient_id IS NOT NULL AND guest_name IS NULL AND guest_phone IS NULL AND guest_erased_at IS NULL)
    OR (patient_id IS NULL AND guest_name IS NOT NULL AND guest_phone IS NOT NULL AND guest_erased_at IS NULL)
    OR (patient_id IS NULL AND guest_name IS NULL AND guest_phone IS NULL AND guest_erased_at IS NOT NULL)
  ),
  -- BR-09: concurrent bookings of the same time cannot both succeed (409 TIME_ALREADY_BOOKED)
  CONSTRAINT appointments_no_overlap
    EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE (status = 'BOOKED')
);
CREATE INDEX appointments_starts_at_idx ON appointments (starts_at);
CREATE INDEX appointments_patient_id_starts_at_idx ON appointments (patient_id, starts_at);
CREATE INDEX appointments_booked_guest_phone_idx ON appointments (guest_phone) WHERE status = 'BOOKED';

-- Append-only: the application role may only SELECT and INSERT (V004).
CREATE TABLE audit_events (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id  uuid REFERENCES users (id), -- NULL for anonymous requests
  action    text NOT NULL CHECK (action IN ( -- AuditAction in backend/openapi.yaml
    'USER_REGISTERED', 'INVITATION_CREATED', 'INVITATION_ACCEPTED', 'LOGIN', 'LOGOUT',
    'MFA_ENROLLED', 'MFA_VERIFIED', 'MFA_RECOVERY_CODE_USED', 'MFA_RESET', 'ADMIN_BOOTSTRAPPED',
    'PASSWORD_CHANGED', 'ACCOUNT_DELETED', 'ROLE_CHANGED', 'USER_DEACTIVATED', 'USER_REACTIVATED',
    'PASSWORD_RESET_CODE_ISSUED', 'PASSWORD_RESET', 'WORKING_HOURS_CHANGED', 'ABSENCE_CREATED',
    'ABSENCE_DELETED', 'APPOINTMENT_BOOKED', 'APPOINTMENT_RESCHEDULED', 'APPOINTMENT_CANCELLED',
    'APPOINTMENT_ACCESS_GRANTED', 'APPOINTMENT_ACCESS_EXPIRED', 'APPOINTMENT_DATA_ACCESSED',
    'SETTINGS_UPDATED', 'ACCESS_DENIED'
  )),
  -- <type>:<uuid>, never personal data
  target    text CHECK (char_length(target) <= 100 AND target ~ '^[a-z_]+:[0-9a-f-]{36}$'),
  ip        inet,
  timestamp timestamptz NOT NULL DEFAULT now(),
  outcome   text NOT NULL CHECK (outcome IN ('SUCCESS', 'FAILURE', 'DENIED')),
  -- allow-listed keys only, e.g. oldStartsAt/newStartsAt for a rescheduling (BR-22)
  details   jsonb CHECK (jsonb_typeof(details) = 'object')
);
CREATE INDEX audit_events_timestamp_idx ON audit_events (timestamp DESC);
CREATE INDEX audit_events_actor_id_timestamp_idx ON audit_events (actor_id, timestamp);
CREATE INDEX audit_events_action_timestamp_idx ON audit_events (action, timestamp);
