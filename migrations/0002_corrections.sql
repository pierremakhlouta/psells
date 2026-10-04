-- Migration 0002: the corrections log, added for fixing records.
--
-- schema.sql runs only when the pgdata volume is first created, so a database
-- made before this never sees the table. This file brings such a database
-- level with schema.sql. A new database needs nothing from here: schema.sql
-- already ends with the same section. Apply 0001 first if the database is
-- older still.
--
-- It only adds. No existing table, row or view is touched.
--
-- Apply it once, after a backup, from the repository folder:
--
--     ./backup.sh
--     docker compose exec -T db sh -c \
--         'psql -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
--         < migrations/0002_corrections.sql
--
-- Run twice, the second run stops at "relation corrections already exists"
-- and changes nothing. No BEGIN or COMMIT, for the reason 0001 gives.
--
-- The statements below must stay identical in effect to the Corrections
-- section of schema.sql; tests/test_schema.py compares the two. The reasons
-- for each column are written there.

CREATE TABLE corrections (
    id           integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at           timestamptz NOT NULL DEFAULT now(),
    record_type  text        NOT NULL
                 CHECK (record_type IN ('sale', 'return', 'payment')),
    record_id    integer     NOT NULL,
    action       text        NOT NULL CHECK (action IN ('edit', 'delete')),
    before       jsonb       NOT NULL,
    after        jsonb,
    CONSTRAINT after_only_for_an_edit
        CHECK ((action = 'edit') = (after IS NOT NULL))
);

CREATE FUNCTION corrections_are_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'corrections are append-only: % refused', TG_OP;
END;
$$;

CREATE TRIGGER corrections_append_only
    BEFORE UPDATE OR DELETE ON corrections
    FOR EACH ROW EXECUTE FUNCTION corrections_are_append_only();

-- Every correction of one record, for reading its history.

CREATE INDEX idx_corrections_record ON corrections(record_type, record_id);
