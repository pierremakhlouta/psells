-- The workflow: what PSells needs for two people to research, photograph and
-- list items. Applied once, by hand, after a backup, with psql's
-- --single-transaction, so a failure anywhere changes nothing; see
-- RUNBOOK.md, "Apply a migration". schema.sql's last section, Workflow, is
-- this file exactly, and tests/test_schema.py holds the two equal.
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
