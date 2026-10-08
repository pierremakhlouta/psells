-- The role the analytics ETL reads the business database as: psells_etl,
-- which can read the four business tables and the products view and do
-- nothing else. Not the login's tables (users, sessions), not the
-- corrections log, and no write of any kind, so a bug, or a compromised
-- package in the analytics image, cannot change a record.
--
-- Run by the database's owner, and safe to run again: it creates the role if
-- it is missing and sets its grants to exactly these, whatever they were.
-- It sets no password and cannot log in until one is set;
-- analytics/create-etl-role.sh does both, from .env, after this file.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'psells_etl') THEN
        CREATE ROLE psells_etl NOLOGIN;
    END IF;
END
$$;

-- Exactly these grants: whatever else it was given is taken away first.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM psells_etl;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM psells_etl;
GRANT USAGE ON SCHEMA public TO psells_etl;
GRANT SELECT ON products, sales, returns, payments, products_view TO psells_etl;

-- Every transaction it starts is read-only. The grants already stop a
-- write; this makes one fail with a sentence that says why.
ALTER ROLE psells_etl SET default_transaction_read_only = on;
