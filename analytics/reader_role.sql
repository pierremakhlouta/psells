-- The role the app reads the warehouse as: psells_reader, which can read the
-- five views of analytics/views.sql and nothing else. Not the tables under
-- them, and no write of any kind. A view reads its tables with its owner's
-- rights, so the views alone are enough.
--
-- The grant on the views is in views.sql, not here: the ETL drops and makes
-- the views again on every run, and a grant goes with the view it was on, so
-- it is given again each time, in the same transaction.
--
-- Run by the warehouse's owner, and safe to run again. It sets no password
-- and cannot log in until one is set; analytics/create-reader-role.sh does
-- both, from .env, after this file.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'psells_reader') THEN
        CREATE ROLE psells_reader NOLOGIN;
    END IF;
END
$$;

-- Only what views.sql grants: whatever else it was given is taken away.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM psells_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM psells_reader;
GRANT USAGE ON SCHEMA public TO psells_reader;

ALTER ROLE psells_reader SET default_transaction_read_only = on;
