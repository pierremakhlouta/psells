-- When an item's price was last reviewed on the Price drops page. Applied
-- once, by hand, after a backup, with psql's --single-transaction; see
-- RUNBOOK.md, "Apply a migration". schema.sql's last section, Price review,
-- is this file exactly, and tests/test_schema.py holds the two equal.
--
-- Pressing Reviewed, or changing a listed item's listed price, sets it to
-- the day. A reviewed item leaves the Price drops list until it has gone
-- another stale_listing_days without selling. Empty for an item never
-- reviewed.

ALTER TABLE products ADD COLUMN price_reviewed_on date;

-- products_view is made again to carry the new column, and its grant to the
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
