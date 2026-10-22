-- Listing as Pierre does it: an item is ready once its information and its
-- photos are in, and listed when he says it is posted, not when it gets a
-- listed price. Applied once, by hand, after a backup, with psql's
-- --single-transaction; see RUNBOOK.md, "Apply a migration". schema.sql's
-- last section, Listing, is this file exactly, and tests/test_schema.py holds
-- the two equal.
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
