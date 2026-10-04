-- Invented sample records for PSells, in the current schema.
--
-- Apply to an empty database created from schema.sql. The README shows how,
-- in a Compose project of its own so it can never land in the real database.
--
-- Each INSERT names its id, so the rows reference each other the same way on
-- every run. Ids are GENERATED ALWAYS, which refuses an id supplied by an
-- INSERT unless it says OVERRIDING SYSTEM VALUE. The setval lines at the end
-- then move each sequence past the highest id, so the next row added through
-- the application gets 10, 7, 4 and 4 rather than colliding with these.
--
-- None of this is real. The partner percentage in sample_data/config.json
-- is a placeholder too, and each sale's frozen cut is what that percentage,
-- or the product's own share, gives. tests/test_seed.py holds these rows to
-- what they are meant to show:
--
--   In stock: 1, 3, 4, 5, 6 and 7, two of them glasses (6 and 7), one
--   discontinued at retail (4), one with a return (5).
--   Out of stock, one for each reason: 2 sold out, 8 returned, 9 a mix of
--   sold and returned.
--   Sales on different dates, two of them on 2026-08-08, two of more than
--   one unit; all three partner-share modes.
--   Three returns with notes, on different dates, and three payments.

BEGIN;

INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (1, 'Watches', 'Chrono Steel Watch 42mm', 3, 20000, 14000, 0, 'default', NULL, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (2, 'Watches', 'Trailrunner GPS Watch', 2, 30000, 22000, 0, 'custom_percent', 40.0, NULL, 'Used (Like New)', 'no box');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (3, 'Hats', 'Canvas Field Cap', 5, 4500, 3000, 0, 'custom_amount', NULL, 1200, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (4, 'Watches', 'Legacy Dive Watch', 1, 0, 18000, 1, 'custom_amount', NULL, 9000, 'Used (Good)', 'no box, some scratches on the bezel');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (5, 'Cups', 'Insulated Travel Mug 500ml', 6, 5500, 3500, 0, 'default', NULL, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (6, 'Glasses', 'Polarised Sunglasses Matte Black', 2, 16000, 11000, 0, 'custom_percent', 25.0, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (7, 'Glasses', 'Blue Light Glasses Round Frame', 4, 3000, 2200, 0, 'default', NULL, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (8, 'Bags', 'Canvas Tote Bag Natural', 2, 4000, 2500, 0, 'default', NULL, NULL, 'Brand New', '');
INSERT INTO products OVERRIDING SYSTEM VALUE VALUES (9, 'Hats', 'Wool Beanie Charcoal', 3, 3500, 2500, 0, 'custom_amount', NULL, 800, 'Brand New', '');

INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (1, '2026-05-14', 1, 1, 15000, 6000);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (2, '2026-06-02', 2, 2, 21000, 12000);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (3, '2026-07-19', 3, 1, 2800, 1200);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (4, '2026-08-08', 9, 2, 2400, 800);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (5, '2026-08-08', 6, 1, 10500, 4000);
INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES (6, '2026-09-12', 5, 1, 3500, 1650);

INSERT INTO returns OVERRIDING SYSTEM VALUE VALUES (1, '2026-06-30', 5, 2, 'unsold, sent back to the partner');
INSERT INTO returns OVERRIDING SYSTEM VALUE VALUES (2, '2026-08-20', 8, 2, 'print faded in the window, both sent back');
INSERT INTO returns OVERRIDING SYSTEM VALUE VALUES (3, '2026-09-03', 9, 1, 'stretched cuff');

INSERT INTO payments OVERRIDING SYSTEM VALUE VALUES (1, '2026-06-05', 15000, 'Cash');
INSERT INTO payments OVERRIDING SYSTEM VALUE VALUES (2, '2026-07-25', 4000, 'e-transfer');
INSERT INTO payments OVERRIDING SYSTEM VALUE VALUES (3, '2026-09-15', 10000, 'e-transfer');

SELECT setval(pg_get_serial_sequence('products', 'id'), (SELECT max(id) FROM products));
SELECT setval(pg_get_serial_sequence('sales', 'id'), (SELECT max(id) FROM sales));
SELECT setval(pg_get_serial_sequence('returns', 'id'), (SELECT max(id) FROM returns));
SELECT setval(pg_get_serial_sequence('payments', 'id'), (SELECT max(id) FROM payments));

COMMIT;
