-- PSells database schema, PostgreSQL.
--
-- Applied once, to an empty database. The Compose stack mounts this file into
-- the database container's /docker-entrypoint-initdb.d, so PostgreSQL runs it
-- the first time the pgdata volume is created and never again. The tests apply
-- it to their own database at the start of every run.
--
-- It was translated from the SQLite schema PSells used until Phase 04, which is
-- in the git history. Every rule is the same rule; what changed is only how
-- each one is written. The differences, and why:
--
--   No STRICT and no PRAGMA foreign_keys. PostgreSQL enforces declared types
--   and foreign keys always, on every connection, with nothing to switch on.
--
--   Ids are GENERATED ALWAYS AS IDENTITY. A sequence hands them out and never
--   hands out the same one twice, so deleting the newest product no longer
--   frees its id for the next one. ALWAYS means an INSERT cannot supply its own
--   id unless it says OVERRIDING SYSTEM VALUE; only loading existing records
--   (the migration, the sample data, the test helpers) does that, and each then
--   moves the sequence past the highest id.
--
--   Dates are the DATE type rather than text with a CHECK. The type itself
--   refuses 2026-02-30, so the three *_date_valid constraints are gone.
--
--   partner_share_percent is double precision, the same eight-byte number
--   SQLite's REAL is, so a stored percentage reads back exactly as before.
--   PostgreSQL's own "real" is four bytes and would not.
--
--   Money stays integer, not bigint. SUM over an integer column returns bigint,
--   which Python reads as int. SUM over bigint returns numeric, which Python
--   reads as Decimal, and integer cents would quietly stop being integers.


-- Products ------------------------------------------------------------------
--
-- quantity_received is the original intake. It is never changed by recording a
-- sale or a return. Units sold, units returned and units available are derived
-- from the sales and returns tables; see products_view at the end.

CREATE TABLE products (
    id                          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category                    text    NOT NULL CHECK (length(trim(category)) > 0),
    name                        text    NOT NULL CHECK (length(trim(name)) > 0),
    quantity_received           integer NOT NULL CHECK (quantity_received >= 1),
    retail_price_cents          integer NOT NULL CHECK (retail_price_cents >= 0),
    listed_price_cents          integer NOT NULL CHECK (listed_price_cents >= 0),
    retail_discontinued         integer NOT NULL CHECK (retail_discontinued IN (0, 1)),
    partner_share_mode          text    NOT NULL
                                CONSTRAINT partner_share_mode_valid CHECK (
                                    partner_share_mode IN (
                                        'default',
                                        'custom_percent',
                                        'custom_amount')),
    -- PostgreSQL sorts NaN above every number, so BETWEEN refuses it here.
    -- SQLite stored NaN as NULL instead; the application refuses it first in
    -- both cases.
    partner_share_percent       double precision CHECK (partner_share_percent BETWEEN 0 AND 100),
    partner_share_amount_cents  integer          CHECK (partner_share_amount_cents >= 0),
    condition                   text    NOT NULL CHECK (length(trim(condition)) > 0),
    notes                       text    NOT NULL,

    -- Each mode allows exactly one shape. Without this, a default-mode product
    -- could carry a stale percentage that nothing would ever read.
    CONSTRAINT partner_share_matrix CHECK (
           (partner_share_mode = 'default'
                AND partner_share_percent      IS NULL
                AND partner_share_amount_cents IS NULL)
        OR (partner_share_mode = 'custom_percent'
                AND partner_share_percent      IS NOT NULL
                AND partner_share_amount_cents IS NULL)
        OR (partner_share_mode = 'custom_amount'
                AND partner_share_percent      IS NULL
                AND partner_share_amount_cents IS NOT NULL)
    ),

    -- retail_discontinued describes the retail market, not PSells stock. A zero
    -- retail price means exactly this situation and nothing else, and such a
    -- product must take a fixed per-unit partner amount, because a percentage
    -- of a price that no longer exists is not a number worth computing.
    CONSTRAINT retail_discontinued_rules CHECK (
           (retail_discontinued = 0
                AND retail_price_cents > 0)
        OR (retail_discontinued = 1
                AND retail_price_cents = 0
                AND partner_share_mode = 'custom_amount')
    )
);


-- Sales ---------------------------------------------------------------------
--
-- partner_share_cents is the per-unit cut frozen at the moment of sale, so
-- later changes to the product never rewrite the profit on past sales.

CREATE TABLE sales (
    id                   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date                 date    NOT NULL,
    item_id              integer NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity             integer NOT NULL CHECK (quantity >= 1),
    sale_price_cents     integer NOT NULL CHECK (sale_price_cents >= 0),
    partner_share_cents  integer NOT NULL CHECK (partner_share_cents >= 0)
);


-- Returns -------------------------------------------------------------------
--
-- Unsold units sent back to the partner. A unit that has already sold cannot
-- be returned; that rule is enforced in the application, not here.

CREATE TABLE returns (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date      date    NOT NULL,
    item_id   integer NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity  integer NOT NULL CHECK (quantity >= 1),
    notes     text    NOT NULL
);


-- Payments ------------------------------------------------------------------
--
-- Payouts against the running balance owed to the partner as a whole. They
-- deliberately do not reference a product or a sale.

CREATE TABLE payments (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date          date    NOT NULL,
    amount_cents  integer NOT NULL CHECK (amount_cents >= 0),
    notes         text    NOT NULL
);


-- Indexes -------------------------------------------------------------------
--
-- PostgreSQL, like SQLite, indexes a primary key automatically but never the
-- child side of a foreign key. Without these, every attempt to delete a product
-- scans the whole sales table and the whole returns table to decide whether to
-- allow it, and so does every lookup of one product's transactions.

CREATE INDEX idx_sales_item_id   ON sales(item_id);
CREATE INDEX idx_returns_item_id ON returns(item_id);


-- Derived view --------------------------------------------------------------
--
-- Rows from this view carry the three derived quantities alongside the stored
-- columns, so application code receives the same shape it used to load from
-- JSON and does not have to compute stock for itself.
--
-- Each table is aggregated in its own subquery before being joined. Joining
-- sales and returns directly would multiply them together: a product with two
-- sales and three returns would produce six rows, and the sums would be wrong
-- in both directions.
--
-- PostgreSQL expands p.* into a fixed list of columns when the view is
-- created. A column added to products later does not appear here until the
-- view is dropped and created again.

CREATE VIEW products_view AS
SELECT
    p.*,
    COALESCE(s.sold, 0)     AS quantity_sold,
    COALESCE(r.returned, 0) AS quantity_returned,
    p.quantity_received - COALESCE(s.sold, 0) - COALESCE(r.returned, 0)
                            AS quantity_available
FROM products p
LEFT JOIN (
    SELECT item_id, SUM(quantity) AS sold
    FROM sales
    GROUP BY item_id
) s ON s.item_id = p.id
LEFT JOIN (
    SELECT item_id, SUM(quantity) AS returned
    FROM returns
    GROUP BY item_id
) r ON r.item_id = p.id;


-- Authentication ------------------------------------------------------------
--
-- Added in Phase 05b. A database created before then gets these tables from
-- migrations/0001_authentication.sql instead, which must create exactly what
-- this section does; tests/test_schema.py builds a database both ways and
-- compares them. Keep this section after every table that came before it,
-- with only later migrations' sections below, because that test takes everything
-- above its heading as the schema the migration was written against.
--
-- One account today, Pierre's. A table rather than a setting, so a second
-- person later is a row, not a redesign.
--
-- password_hash is the whole string Argon2 produces: the algorithm, its
-- parameters, the salt and the hash together. The check refuses anything that
-- is not Argon2id, so a plain password cannot be stored here by mistake.

CREATE TABLE users (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       text    NOT NULL UNIQUE
                   CHECK (length(username) > 0 AND username = trim(username)),
    password_hash  text    NOT NULL CHECK (password_hash LIKE '$argon2id$%')
);

-- One row per login. The cookie carries a long random value; only its SHA-256
-- digest is kept, so a copy of the database or of a backup holds nothing a
-- browser could present. Logging out deletes the row.
--
-- Whether a session has expired is worked out from the two times, never
-- stored: it ends 2 hours after last_seen_at, or 12 hours after created_at,
-- whichever comes first. The application sets both times from its own clock,
-- so there are no defaults here.
--
-- form_token is the value every form must send back. It is not secret from
-- the person logged in, whose pages show it, only from other sites, so it is
-- kept as it is rather than hashed.
--
-- Deleting a user deletes their sessions with them.

CREATE TABLE sessions (
    token_digest  bytea       PRIMARY KEY CHECK (length(token_digest) = 32),
    user_id       integer     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    form_token    text        NOT NULL CHECK (length(form_token) >= 32),
    created_at    timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    CONSTRAINT session_times_in_order CHECK (last_seen_at >= created_at)
);

-- Ending every session of one user, which changing the password does, would
-- otherwise scan the whole table.

CREATE INDEX idx_sessions_user_id ON sessions(user_id);


-- Corrections ---------------------------------------------------------------
--
-- Added for fixing records. A database created before then gets this section
-- from migrations/0002_corrections.sql instead, which must create exactly what
-- it does; tests/test_schema.py compares them. Keep it last, after
-- Authentication, for the same reason.
--
-- A sale, return or payment can be edited or deleted to correct a mistake.
-- Each correction writes one row here, in the same transaction as the change,
-- so the figures can be corrected and what was corrected is still known.
--
-- before is the record as it was and after as it became, each the whole row
-- as JSON. A delete has no after, and the constraint below holds that. There
-- is no foreign key to the record: after a delete it no longer exists, and
-- this row is the only trace of it.
--
-- The application never changes or removes a row here, and the trigger makes
-- that the database's rule too: an UPDATE or DELETE is refused. Restoring a
-- backup, or TRUNCATE, which no row trigger sees, is still possible to whoever
-- holds the database itself.

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


-- Workflow ------------------------------------------------------------------
--
-- Added for the shared workflow. A database created before then gets this
-- section from migrations/0003_workflow.sql instead, which is this section
-- exactly; tests/test_schema.py compares them. Keep it last, after
-- Corrections, for the same reason. On a new database its statements about
-- existing products find none.
--
-- Categories and conditions become lists to choose from. Each is a table of
-- names; products keep the name, and a foreign key on it refuses any name
-- not on the list, while ON UPDATE CASCADE carries a renamed one to every
-- product that has it. A hidden one stays, for the products and history that
-- have it, and is not offered for a new item.
--
-- An item can now arrive before it is researched, so its condition, retail
-- price and listed price may be empty until someone fills them in. The stage
-- an item has reached is worked out from what it has, never stored.

CREATE TABLE categories (
    name    text    PRIMARY KEY
            CHECK (length(name) > 0 AND name = trim(name)),
    hidden  boolean NOT NULL DEFAULT false
);

-- position orders the conditions the way they read, best first, rather than
-- alphabetically.
CREATE TABLE conditions (
    name      text    PRIMARY KEY
              CHECK (length(name) > 0 AND name = trim(name)),
    position  integer NOT NULL,
    hidden    boolean NOT NULL DEFAULT false
);

INSERT INTO conditions (name, position) VALUES
    ('Brand new', 1), ('Open box', 2), ('Like new', 3), ('Used', 4), ('Damaged', 5);

-- Every category a product already has is on the list. One with nothing in
-- stock when this runs is hidden, so the list starts with what is being sold.
INSERT INTO categories (name)
SELECT DISTINCT category FROM products;

UPDATE categories SET hidden = true
WHERE NOT EXISTS (
    SELECT 1
    FROM products p
    LEFT JOIN (SELECT item_id, SUM(quantity) AS n FROM sales GROUP BY item_id) s
        ON s.item_id = p.id
    LEFT JOIN (SELECT item_id, SUM(quantity) AS n FROM returns GROUP BY item_id) r
        ON r.item_id = p.id
    WHERE p.category = categories.name
      AND p.quantity_received - COALESCE(s.n, 0) - COALESCE(r.n, 0) > 0
);

-- The conditions written so far, onto the list. Any other value makes the
-- foreign key below fail, and with it the whole migration.
UPDATE products SET condition = CASE condition
    WHEN 'Brand New'       THEN 'Brand new'
    WHEN 'brand new'       THEN 'Brand new'
    WHEN 'Like New'        THEN 'Like new'
    WHEN 'Used (Like New)' THEN 'Like new'
    WHEN 'Used (Good)'     THEN 'Used'
    ELSE condition
END;

ALTER TABLE products
    ADD CONSTRAINT products_category_listed
        FOREIGN KEY (category) REFERENCES categories(name) ON UPDATE CASCADE,
    ADD CONSTRAINT products_condition_listed
        FOREIGN KEY (condition) REFERENCES conditions(name) ON UPDATE CASCADE,
    ALTER COLUMN condition DROP NOT NULL,
    ALTER COLUMN retail_price_cents DROP NOT NULL,
    ALTER COLUMN listed_price_cents DROP NOT NULL,
    -- The average price the item sells for on Facebook Marketplace.
    ADD COLUMN marketplace_price_cents integer
        CHECK (marketplace_price_cents >= 0),
    -- What the listing says beyond the template: accessories, quantities,
    -- marks. Empty when there is nothing to add.
    ADD COLUMN details text NOT NULL DEFAULT '',
    -- Whether the item is also posted on Instagram; every listed item is on
    -- Facebook.
    ADD COLUMN on_instagram boolean NOT NULL DEFAULT false,
    -- When it arrived. Products from before this have none: nobody recorded it.
    ADD COLUMN arrived_on date,
    -- When a listed price was first entered.
    ADD COLUMN listed_on date,
    -- Raised by every save of the product, so a save made from a page opened
    -- before someone else's is refused rather than silently undoing it.
    ADD COLUMN version integer NOT NULL DEFAULT 1;

-- A new item arrives today unless it says otherwise; the existing ones keep
-- their empty date.
ALTER TABLE products ALTER COLUMN arrived_on SET DEFAULT CURRENT_DATE;

-- A retail price may now be missing, until researched. A product
-- discontinued at retail still has 0 and a fixed payout, as before.
ALTER TABLE products DROP CONSTRAINT retail_discontinued_rules;
ALTER TABLE products ADD CONSTRAINT retail_discontinued_rules CHECK (
       (retail_discontinued = 0
            AND (retail_price_cents IS NULL OR retail_price_cents > 0))
    OR (retail_discontinued = 1
            AND retail_price_cents = 0
            AND partner_share_mode = 'custom_amount')
);

-- Photos are files on disk; a row says which item each belongs to. A
-- product with photos cannot be deleted until they are, so no file is left
-- behind without its row.
CREATE TABLE photos (
    id          integer     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id  integer     NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    file_name   text        NOT NULL UNIQUE CHECK (length(file_name) > 0),
    added_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_photos_product_id ON photos(product_id);

-- The two listing templates, empty until written on the settings page, so
-- their wording, pickup areas and hashtags are never in this repository.
CREATE TABLE listing_templates (
    platform  text PRIMARY KEY CHECK (platform IN ('facebook', 'instagram')),
    body      text NOT NULL
);

INSERT INTO listing_templates (platform, body) VALUES
    ('facebook', ''), ('instagram', '');

-- products_view lists the products' columns as they were when it was made,
-- so it is made again to carry the new ones. Dropping it drops its grant to
-- the ETL's read-only role, given back here where that role exists.
DROP VIEW products_view;

CREATE VIEW products_view AS
SELECT
    p.*,
    COALESCE(s.sold, 0)     AS quantity_sold,
    COALESCE(r.returned, 0) AS quantity_returned,
    p.quantity_received - COALESCE(s.sold, 0) - COALESCE(r.returned, 0)
                            AS quantity_available
FROM products p
LEFT JOIN (
    SELECT item_id, SUM(quantity) AS sold
    FROM sales
    GROUP BY item_id
) s ON s.item_id = p.id
LEFT JOIN (
    SELECT item_id, SUM(quantity) AS returned
    FROM returns
    GROUP BY item_id
) r ON r.item_id = p.id;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'psells_etl') THEN
        GRANT SELECT ON products_view TO psells_etl;
    END IF;
END
$$;

-- Listing ---------------------------------------------------------------------
--
-- Added when listing became a tick. A database created before then gets this
-- section from migrations/0004_listing.sql instead, which is this section
-- exactly; tests/test_schema.py compares them. Keep it last. On a new
-- database its statements about existing products find none.
--
-- Two facts per product. photos_required: whether the item needs a photo
-- before it is ready to list; every product that exists when this is applied
-- is counted as photographed, so nobody is asked to photograph old stock, and
-- each new one needs one. listed: ticked when the item is posted; every
-- existing product with a listed price was posted before this existed, so it
-- is ticked. listed_on, from 0003, now dates the tick: it is set when listed
-- is ticked, emptied when it is unticked, and a listed item needs a listed
-- price.

ALTER TABLE products
    ADD COLUMN photos_required boolean NOT NULL DEFAULT false,
    ADD COLUMN listed boolean NOT NULL DEFAULT false;

UPDATE products SET listed = true WHERE listed_price_cents IS NOT NULL;

-- From here on, a new product needs its photos.
ALTER TABLE products ALTER COLUMN photos_required SET DEFAULT true;

ALTER TABLE products ADD CONSTRAINT listed_rules CHECK (
        (NOT listed OR listed_price_cents IS NOT NULL)
    AND (listed OR listed_on IS NULL)
);

-- products_view is made again to carry the new columns, and its grant to the
-- ETL's read-only role given back where that role exists, as in 0003.
DROP VIEW products_view;

CREATE VIEW products_view AS
SELECT
    p.*,
    COALESCE(s.sold, 0)     AS quantity_sold,
    COALESCE(r.returned, 0) AS quantity_returned,
    p.quantity_received - COALESCE(s.sold, 0) - COALESCE(r.returned, 0)
                            AS quantity_available
FROM products p
LEFT JOIN (
    SELECT item_id, SUM(quantity) AS sold
    FROM sales
    GROUP BY item_id
) s ON s.item_id = p.id
LEFT JOIN (
    SELECT item_id, SUM(quantity) AS returned
    FROM returns
    GROUP BY item_id
) r ON r.item_id = p.id;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'psells_etl') THEN
        GRANT SELECT ON products_view TO psells_etl;
    END IF;
END
$$;
