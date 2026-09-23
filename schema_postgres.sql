-- PSells database schema, PostgreSQL.
--
-- The translation of schema.sql, which is the SQLite schema the application
-- uses today. Every rule is the same rule; what changed is only how each one is
-- written. This file replaces schema.sql when the application moves over.
--
-- Differences from the SQLite schema, and why:
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
