-- The warehouse's views: the business questions, answered once, in SQL, for
-- whatever shows them. analytics/etl.py makes them right after it fills the
-- tables, in the same transaction, and warehouse.sql drops them first.
--
-- Each new figure is worked out here and nowhere else: margin, sell-through,
-- shares and ranks. The page that shows them reads these views and works out
-- nothing. Money stays whole cents. A ratio is left unrounded, as a fraction
-- (0.25, not 25), and NULL where its denominator is zero; rounding it is for
-- whatever displays it.
--
-- Margin is profit over revenue, summed first: a month's or a category's
-- margin is its total profit over its total revenue, never an average of each
-- sale's. Sell-through is units sold over units received; a unit returned to
-- the partner counts as not sold.


-- Every month from the first event to the last, a month without a sale
-- included as zeros, so a trend shows its gaps.
CREATE VIEW sales_by_month AS
WITH months AS (
    SELECT DISTINCT date_trunc('month', date)::date AS month FROM dim_date
),
sold AS (
    SELECT date_trunc('month', date)::date AS month,
           count(*)                AS sales,
           sum(quantity)           AS units,
           sum(sale_total_cents)   AS revenue_cents,
           sum(partner_cut_cents)  AS partner_cut_cents,
           sum(profit_cents)       AS profit_cents
    FROM fact_sales
    GROUP BY 1
),
monthly AS (
    SELECT m.month,
           COALESCE(s.sales, 0)::bigint             AS sales,
           COALESCE(s.units, 0)::bigint             AS units,
           COALESCE(s.revenue_cents, 0)::bigint     AS revenue_cents,
           COALESCE(s.partner_cut_cents, 0)::bigint AS partner_cut_cents,
           COALESCE(s.profit_cents, 0)::bigint      AS profit_cents
    FROM months m LEFT JOIN sold s USING (month)
)
SELECT month,
       extract(year FROM month)::int                   AS year,
       extract(month FROM month)::int                  AS month_number,
       to_char(month, 'FMMonth')                       AS month_name,
       sales, units, revenue_cents, partner_cut_cents, profit_cents,
       profit_cents::numeric / NULLIF(revenue_cents, 0) AS margin,
       (sum(revenue_cents) OVER (ORDER BY month))::bigint
                                                       AS cumulative_revenue_cents,
       revenue_cents - lag(revenue_cents) OVER (ORDER BY month)
                                                       AS revenue_change_cents
FROM monthly;


-- The same by ISO week, Monday to Sunday, every week from the first event to
-- the last.
CREATE VIEW sales_by_week AS
WITH weeks AS (
    SELECT DISTINCT date_trunc('week', date)::date AS week_start FROM dim_date
),
sold AS (
    SELECT date_trunc('week', date)::date AS week_start,
           count(*)               AS sales,
           sum(quantity)          AS units,
           sum(sale_total_cents)  AS revenue_cents,
           sum(partner_cut_cents) AS partner_cut_cents,
           sum(profit_cents)      AS profit_cents
    FROM fact_sales
    GROUP BY 1
)
SELECT w.week_start,
       extract(isoyear FROM w.week_start)::int          AS iso_year,
       extract(week FROM w.week_start)::int             AS iso_week,
       COALESCE(s.sales, 0)::bigint                     AS sales,
       COALESCE(s.units, 0)::bigint                     AS units,
       COALESCE(s.revenue_cents, 0)::bigint             AS revenue_cents,
       COALESCE(s.partner_cut_cents, 0)::bigint         AS partner_cut_cents,
       COALESCE(s.profit_cents, 0)::bigint              AS profit_cents,
       s.profit_cents::numeric / NULLIF(s.revenue_cents, 0) AS margin
FROM weeks w LEFT JOIN sold s USING (week_start);


-- Every category: its stock as psells counts it, what it sold for, and its
-- share of all revenue.
CREATE VIEW category_performance AS
WITH stock AS (
    SELECT category,
           count(*)                AS products,
           count(*) FILTER (WHERE in_stock) AS products_in_stock,
           sum(quantity_received)  AS received,
           sum(quantity_sold)      AS sold,
           sum(quantity_returned)  AS returned,
           sum(quantity_available) AS available
    FROM dim_product
    GROUP BY category
),
money AS (
    SELECT p.category,
           sum(f.sale_total_cents)  AS revenue_cents,
           sum(f.partner_cut_cents) AS partner_cut_cents,
           sum(f.profit_cents)      AS profit_cents
    FROM fact_sales f JOIN dim_product p USING (product_id)
    GROUP BY p.category
)
SELECT category,
       products::bigint, products_in_stock::bigint,
       received::bigint, sold::bigint, returned::bigint, available::bigint,
       COALESCE(revenue_cents, 0)::bigint     AS revenue_cents,
       COALESCE(partner_cut_cents, 0)::bigint AS partner_cut_cents,
       COALESCE(profit_cents, 0)::bigint      AS profit_cents,
       profit_cents::numeric / NULLIF(revenue_cents, 0) AS margin,
       sold::numeric / NULLIF(received, 0)              AS sell_through,
       COALESCE(revenue_cents, 0)::numeric
           / NULLIF(sum(COALESCE(revenue_cents, 0)) OVER (), 0) AS revenue_share
FROM stock LEFT JOIN money USING (category);


-- Every product, sold or not, with its ranks: overall by units, revenue and
-- profit, and within its category by profit. Ties share a rank, as rank()
-- gives them. The best sellers are the top of a rank; the worst, its bottom.
CREATE VIEW product_performance AS
WITH money AS (
    SELECT product_id,
           count(*)                 AS sales,
           sum(sale_total_cents)    AS revenue_cents,
           sum(partner_cut_cents)   AS partner_cut_cents,
           sum(profit_cents)        AS profit_cents
    FROM fact_sales
    GROUP BY product_id
),
products AS (
    SELECT p.product_id, p.category, p.name, p.in_stock,
           p.quantity_received  AS received,
           p.quantity_sold      AS sold,
           p.quantity_returned  AS returned,
           p.quantity_available AS available,
           COALESCE(m.sales, 0)::bigint             AS sales,
           COALESCE(m.revenue_cents, 0)::bigint     AS revenue_cents,
           COALESCE(m.partner_cut_cents, 0)::bigint AS partner_cut_cents,
           COALESCE(m.profit_cents, 0)::bigint      AS profit_cents
    FROM dim_product p LEFT JOIN money m USING (product_id)
)
SELECT *,
       profit_cents::numeric / NULLIF(revenue_cents, 0) AS margin,
       sold::numeric / NULLIF(received, 0)              AS sell_through,
       rank() OVER (ORDER BY sold DESC)                 AS rank_by_units,
       rank() OVER (ORDER BY revenue_cents DESC)        AS rank_by_revenue,
       rank() OVER (ORDER BY profit_cents DESC)         AS rank_by_profit,
       rank() OVER (PARTITION BY category ORDER BY profit_cents DESC)
                                                        AS rank_in_category_by_profit
FROM products;


-- The headline figures, one row, with how fresh they are.
CREATE VIEW kpis AS
WITH stock AS (
    SELECT count(*)                         AS products,
           count(*) FILTER (WHERE in_stock) AS products_in_stock,
           COALESCE(sum(quantity_received), 0)  AS received,
           COALESCE(sum(quantity_sold), 0)      AS sold,
           COALESCE(sum(quantity_returned), 0)  AS returned,
           COALESCE(sum(quantity_available), 0) AS available
    FROM dim_product
),
money AS (
    SELECT count(*)                            AS sales,
           COALESCE(sum(sale_total_cents), 0)  AS revenue_cents,
           COALESCE(sum(partner_cut_cents), 0) AS partner_cut_cents,
           COALESCE(sum(profit_cents), 0)      AS profit_cents,
           min(date) AS first_sale, max(date) AS last_sale
    FROM fact_sales
),
paid AS (
    SELECT COALESCE(sum(amount_cents), 0) AS paid_cents FROM fact_payments
)
SELECT products::bigint, products_in_stock::bigint,
       received::bigint, sold::bigint, returned::bigint, available::bigint,
       sales::bigint,
       revenue_cents::bigint, partner_cut_cents::bigint, profit_cents::bigint,
       paid_cents::bigint,
       (partner_cut_cents - paid_cents)::bigint      AS balance_owing_cents,
       profit_cents::numeric / NULLIF(revenue_cents, 0) AS margin,
       sold::numeric / NULLIF(received, 0)              AS sell_through,
       first_sale, last_sale,
       (SELECT finished_at FROM etl_run)                AS built_at
FROM stock, money, paid;
