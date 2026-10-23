-- The two single-row tables are filled here, not by dev seed data, so a fresh database works
-- without seeding. The application role can update these rows but neither insert nor delete them.

-- updated_by_id IS NULL: the practice setup is still pending (BR-18)
INSERT INTO practice_settings (id, practice_name, cancellation_deadline_hours, appointment_minutes, updated_at, updated_by_id)
VALUES (1, 'Doctor Holiday', 24, 15, now(), NULL);

-- the first login locks this row (BR-04)
INSERT INTO admin_bootstrap (id, bootstrapped, admin_id, bootstrapped_at)
VALUES (1, false, NULL, NULL);
