-- Least privilege for the role the running backend uses (backend/README.md, "Database roles").
-- doctorholiday_app is created by infrastructure/postgres/init/00-roles.sh. It has no DDL rights
-- and no TRUNCATE; DELETE only where the domain deletes rows; audit_events is append-only.
-- A migration that adds a table grants on it in the same file.

GRANT SELECT, INSERT, UPDATE         ON users                TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON credentials          TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON sessions             TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON recovery_codes       TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_codes TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE         ON invitations          TO doctorholiday_app;
GRANT SELECT, UPDATE                 ON practice_settings    TO doctorholiday_app;
GRANT SELECT, UPDATE                 ON admin_bootstrap      TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE         ON admin_access_grants  TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON working_hours        TO doctorholiday_app;
GRANT SELECT, INSERT, DELETE         ON absences             TO doctorholiday_app;
GRANT SELECT, INSERT, UPDATE         ON appointments         TO doctorholiday_app;
GRANT SELECT, INSERT                 ON audit_events         TO doctorholiday_app;
