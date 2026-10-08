-- The warehouse's tables, made afresh by analytics/etl.py on every run, in
-- the same transaction that fills them, so a reader sees the last complete
-- run or this one, never half of either.
--
-- Everything here is derived from the business database and can be made
-- again from it; nothing is ever edited in place. A star: one fact table per
-- kind of event, each row pointing at the product and the day it concerns.
-- Money is whole cents, as everywhere in PSells; turning it into dollars is
-- for whatever displays it.

DROP TABLE IF EXISTS fact_sales, fact_returns, fact_payments, dim_product,
    dim_date, etl_run;

-- One row per product, as psells' products_view has it, with the stock
-- psells works out. retail_price_cents is NULL for a product discontinued at
-- retail, which the business database stores as 0: here it means "no retail
-- price", so averages and comparisons leave it out.
CREATE TABLE dim_product (
    product_id                 integer PRIMARY KEY,
    category                   text    NOT NULL,
    name                       text    NOT NULL,
    condition                  text    NOT NULL,
    retail_discontinued        boolean NOT NULL,
    retail_price_cents         integer,
    listed_price_cents         integer NOT NULL,
    partner_share_mode         text    NOT NULL,
    partner_share_percent      double precision,
    partner_share_amount_cents integer,
    quantity_received          integer NOT NULL,
    quantity_sold              integer NOT NULL,
    quantity_returned          integer NOT NULL,
    quantity_available         integer NOT NULL,
    CHECK ((retail_price_cents IS NULL) = retail_discontinued)
);

-- Every day from the first event to the last, with what a report groups by.
CREATE TABLE dim_date (
    date         date     PRIMARY KEY,
    year         smallint NOT NULL,
    quarter      smallint NOT NULL,
    month        smallint NOT NULL,
    month_name   text     NOT NULL,
    iso_week     smallint NOT NULL,
    day_of_week  smallint NOT NULL,  -- 1 Monday to 7 Sunday, as ISO counts
    day_name     text     NOT NULL,
    is_weekend   boolean  NOT NULL
);

-- One row per sale, with the three figures psells' sales_history works out
-- from the sale's own frozen columns.
CREATE TABLE fact_sales (
    sale_id             integer PRIMARY KEY,
    date                date    NOT NULL REFERENCES dim_date,
    product_id          integer NOT NULL REFERENCES dim_product,
    quantity            integer NOT NULL,
    sale_price_cents    integer NOT NULL,
    partner_share_cents integer NOT NULL,
    sale_total_cents    bigint  NOT NULL,
    partner_cut_cents   bigint  NOT NULL,
    profit_cents        bigint  NOT NULL
);

CREATE TABLE fact_returns (
    return_id  integer PRIMARY KEY,
    date       date    NOT NULL REFERENCES dim_date,
    product_id integer NOT NULL REFERENCES dim_product,
    quantity   integer NOT NULL
);

CREATE TABLE fact_payments (
    payment_id   integer PRIMARY KEY,
    date         date    NOT NULL REFERENCES dim_date,
    amount_cents integer NOT NULL
);

-- When the warehouse was last built, and from how many rows: one row, so
-- whatever reads it can say how fresh it is.
CREATE TABLE etl_run (
    finished_at timestamptz NOT NULL,
    products    integer     NOT NULL,
    sales       integer     NOT NULL,
    returns     integer     NOT NULL,
    payments    integer     NOT NULL
);
