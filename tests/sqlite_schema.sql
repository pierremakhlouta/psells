-- The SQLite schema PSells used from Phase 02 until the move to PostgreSQL in
-- Phase 04, kept only so tests/test_migrate.py can build a source database in
-- the exact shape migrate_to_postgres.py reads. The application does not use
-- it; schema.sql at the project root is the schema.
--
-- PSells database schema.
--
-- Applied once to create an empty database:
--     sqlite3 data/psells.db < schema.sql
--
-- Every table is STRICT, so a declared type is enforced rather than advisory.
--
-- Foreign keys are connection-specific in SQLite, and off by default. The line
-- below enables them only for the connection that applies this file. The
-- application must issue PRAGMA foreign_keys = ON on every connection it opens,
-- as the first statement, because the pragma is silently ignored if a
-- transaction is already open.

PRAGMA foreign_keys = ON;


-- Products ------------------------------------------------------------------
--
-- quantity_received is the original intake. It is never changed by recording a
-- sale or a return. Units sold, units returned and units available are derived
-- from the sales and returns tables; see the products_view at the end.

CREATE TABLE products (
    id                          INTEGER PRIMARY KEY,
    category                    TEXT    NOT NULL CHECK (length(trim(category)) > 0),
    name                        TEXT    NOT NULL CHECK (length(trim(name)) > 0),
    quantity_received           INTEGER NOT NULL CHECK (quantity_received >= 1),
    retail_price_cents          INTEGER NOT NULL CHECK (retail_price_cents >= 0),
    listed_price_cents          INTEGER NOT NULL CHECK (listed_price_cents >= 0),
    retail_discontinued         INTEGER NOT NULL CHECK (retail_discontinued IN (0, 1)),
    partner_share_mode          TEXT    NOT NULL
                                CONSTRAINT partner_share_mode_valid CHECK (
                                    partner_share_mode IN (
                                        'default',
                                        'custom_percent',
                                        'custom_amount')),
    partner_share_percent       REAL             CHECK (partner_share_percent BETWEEN 0 AND 100),
    partner_share_amount_cents  INTEGER          CHECK (partner_share_amount_cents >= 0),
    condition                   TEXT    NOT NULL CHECK (length(trim(condition)) > 0),
    notes                       TEXT    NOT NULL,

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
) STRICT;


-- Sales ---------------------------------------------------------------------
--
-- partner_share_cents is the per-unit cut frozen at the moment of sale, so
-- later changes to the product never rewrite the profit on past sales.

CREATE TABLE sales (
    id                   INTEGER PRIMARY KEY,
    date                 TEXT    NOT NULL
                         CONSTRAINT sales_date_valid CHECK ("date" IS date("date")),
    item_id              INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity             INTEGER NOT NULL CHECK (quantity >= 1),
    sale_price_cents     INTEGER NOT NULL CHECK (sale_price_cents >= 0),
    partner_share_cents  INTEGER NOT NULL CHECK (partner_share_cents >= 0)
) STRICT;


-- Returns -------------------------------------------------------------------
--
-- Unsold units sent back to the partner. A unit that has already sold cannot
-- be returned; that rule is enforced in the application, not here.

CREATE TABLE returns (
    id        INTEGER PRIMARY KEY,
    date      TEXT    NOT NULL
              CONSTRAINT returns_date_valid CHECK ("date" IS date("date")),
    item_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity  INTEGER NOT NULL CHECK (quantity >= 1),
    notes     TEXT    NOT NULL
) STRICT;


-- Payments ------------------------------------------------------------------
--
-- Payouts against the running balance owed to the partner as a whole. They
-- deliberately do not reference a product or a sale.

CREATE TABLE payments (
    id            INTEGER PRIMARY KEY,
    date          TEXT    NOT NULL
                  CONSTRAINT payments_date_valid CHECK ("date" IS date("date")),
    amount_cents  INTEGER NOT NULL CHECK (amount_cents >= 0),
    notes         TEXT    NOT NULL
) STRICT;


-- Indexes -------------------------------------------------------------------
--
-- SQLite indexes a primary key automatically but never the child side of a
-- foreign key. Without these, every attempt to delete a product scans the whole
-- sales table and the whole returns table to decide whether to allow it, and so
-- does every lookup of one product's transactions.

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
