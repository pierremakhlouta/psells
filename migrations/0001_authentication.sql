-- Migration 0001: the tables authentication needs, added in Phase 05b.
--
-- schema.sql runs only when the pgdata volume is first created, so a database
-- made before Phase 05b never sees a table added to it later. This file brings
-- such a database level with schema.sql. A new database needs nothing from
-- here: schema.sql already ends with the same section.
--
-- It only adds. No existing table, row or view is touched.
--
-- Apply it once, after a backup, from the repository folder:
--
--     ./backup.sh
--     docker compose exec -T db sh -c \
--         'psql -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
--         < migrations/0001_authentication.sql
--
-- --single-transaction makes it all or nothing, and ON_ERROR_STOP makes psql
-- stop at the first error rather than carry on past it. Run twice, the second
-- run stops at "relation users already exists" and changes nothing.
--
-- There is no BEGIN or COMMIT in this file on purpose: psql supplies the
-- transaction, and the test that applies this file runs it inside a
-- transaction of its own, which a COMMIT here would end early.
--
-- The statements below must stay identical in effect to the Authentication
-- section of schema.sql; tests/test_schema.py compares the two. The reasons
-- for each column are written there.

CREATE TABLE users (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       text    NOT NULL UNIQUE
                   CHECK (length(username) > 0 AND username = trim(username)),
    password_hash  text    NOT NULL CHECK (password_hash LIKE '$argon2id$%')
);

CREATE TABLE sessions (
    token_digest  bytea       PRIMARY KEY CHECK (length(token_digest) = 32),
    user_id       integer     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    form_token    text        NOT NULL CHECK (length(form_token) >= 32),
    created_at    timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    CONSTRAINT session_times_in_order CHECK (last_seen_at >= created_at)
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
