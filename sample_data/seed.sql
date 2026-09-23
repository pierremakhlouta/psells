-- Invented sample records for PSells, in the current schema.
--
-- Apply to an empty database created from schema.sql. The README shows how,
-- in a Compose project of its own so it can never land in the real database.
--
-- Each INSERT names its id, so the rows reference each other the same way on
-- every run. Ids are GENERATED ALWAYS, which refuses an id supplied by an
-- INSERT unless it says OVERRIDING SYSTEM VALUE. The setval lines at the end
-- then move each sequence past the highest id, so the next row added through
-- the application gets 7, 4, 2 and 3 rather than colliding with these.
--
-- None of this is real. The partner percentage in sample_data/config.json
-- is a placeholder too. Between them these rows cover all three
-- partner-share modes, a product discontinued at retail, one that has sold
-- out, a return, and two partner payments.

BEGIN;

INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (1, 'Watches', 'Chrono Steel Watch 42mm', 3, 20000, 14000, 0, 'default', NULL, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (2, 'Watches', 'Trailrunner GPS Watch', 2, 30000, 22000, 0, 'custom_percent', 40.0, NULL, 'Used (Like New)', 'no box');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (3, 'Hats', 'Canvas Field Cap', 5, 4500, 3000, 0, 'custom_amount', NULL, 1200, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (4, 'Watches', 'Legacy Dive Watch', 1, 0, 18000, 1, 'custom_amount', NULL, 9000, 'Used (Good)', 'no box, some scratches on the bezel');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (5, 'Cups', 'Insulated Travel Mug 500ml', 6, 5500, 3500, 0, 'default', NULL, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (6, 'Glasses', 'Polarised Sunglasses Matte Black', 2, 16000, 11000, 0, 'custom_percent', 25.0, NULL, 'Brand New', '');

INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (1, '2026-05-14', 1, 1, 15000, 6000);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (2, '2026-06-02', 2, 2, 21000, 12000);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (3, '2026-07-19', 3, 1, 2800, 1200);

INSERT INTO returns OVERRIDING SYSTEM VALUE VALUES (1, '2026-06-30', 5, 2, 'unsold, sent back to the partner');

INSERT INTO payments OVERRIDING SYSTEM VALUE VALUES (1, '2026-06-05', 15000, 'Cash');
INSERT INTO payments OVERRIDING SYSTEM VALUE VALUES (2, '2026-07-25', 4000, 'e-transfer');

SELECT setval(pg_get_serial_sequence('products', 'id'), (SELECT max(id) FROM products));
SELECT setval(pg_get_serial_sequence('sales', 'id'), (SELECT max(id) FROM sales));
SELECT setval(pg_get_serial_sequence('returns', 'id'), (SELECT max(id) FROM returns));
SELECT setval(pg_get_serial_sequence('payments', 'id'), (SELECT max(id) FROM payments));

COMMIT;
