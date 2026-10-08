"""Build the analytics warehouse from the business database, in full.

Run as the one-off etl container of compose.analytics.yaml:

    docker compose -f compose.yaml -f compose.analytics.yaml run --rm etl

Three steps. Extract asks psells' own readers for every row and figure, as
the read-only psells_etl role, inside one snapshot so a sale recorded while it
runs cannot make the rows and the totals disagree. Transform gives each table
its types and names, makes the date dimension, and blanks the retail price of
a product discontinued at retail; it works out no business figure, because
psells already has. Load recreates the warehouse's tables and fills them in
one transaction, checks the warehouse adds up to psells' own dashboard
figures, makes the views of analytics/views.sql over the tables, and commits
only if every figure is equal.

It prints how many rows it wrote, never a figure: on the Mac the rows are the
real records.
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd
import psycopg
from psycopg import sql
from psycopg.rows import tuple_row

import psells


# Beside this file, wherever it is run from: in the image both are in /app.
HERE = os.path.dirname(os.path.abspath(__file__))
WAREHOUSE_SQL = os.path.join(HERE, "warehouse.sql")
VIEWS_SQL = os.path.join(HERE, "views.sql")

# Each warehouse table's columns, in the order warehouse.sql makes them, with
# the type pandas holds them as. Int64 and boolean are pandas' own types that
# can also hold "missing", where numpy's would turn a missing whole number
# into a float.
TABLES = {
    "dim_date": {
        "date": "object", "year": "Int64", "quarter": "Int64",
        "month": "Int64", "month_name": "string", "iso_week": "Int64",
        "day_of_week": "Int64", "day_name": "string", "is_weekend": "boolean",
    },
    "dim_product": {
        "product_id": "Int64", "category": "string", "name": "string",
        "condition": "string", "retail_discontinued": "boolean",
        "retail_price_cents": "Int64", "listed_price_cents": "Int64",
        "partner_share_mode": "string", "partner_share_percent": "Float64",
        "partner_share_amount_cents": "Int64", "quantity_received": "Int64",
        "quantity_sold": "Int64", "quantity_returned": "Int64",
        "quantity_available": "Int64", "in_stock": "boolean",
    },
    "fact_sales": {
        "sale_id": "Int64", "date": "object", "product_id": "Int64",
        "quantity": "Int64", "sale_price_cents": "Int64",
        "partner_share_cents": "Int64", "sale_total_cents": "Int64",
        "partner_cut_cents": "Int64", "profit_cents": "Int64",
    },
    "fact_returns": {
        "return_id": "Int64", "date": "object", "product_id": "Int64",
        "quantity": "Int64",
    },
    "fact_payments": {
        "payment_id": "Int64", "date": "object", "amount_cents": "Int64",
    },
}

# The warehouse's sums, each the same figure as one of dashboard_totals'.
# Load checks every one before it commits: if the warehouse disagrees with
# psells, the warehouse is wrong, and the previous one stays.
CHECKS = {
    "total_received": "SELECT COALESCE(SUM(quantity_received), 0) FROM dim_product",
    "total_sold": "SELECT COALESCE(SUM(quantity), 0) FROM fact_sales",
    "total_returned": "SELECT COALESCE(SUM(quantity), 0) FROM fact_returns",
    "total_available": "SELECT COALESCE(SUM(quantity_available), 0) FROM dim_product",
    "total_revenue": "SELECT COALESCE(SUM(sale_total_cents), 0) FROM fact_sales",
    "total_partner_share": "SELECT COALESCE(SUM(partner_cut_cents), 0) FROM fact_sales",
    "total_profit": "SELECT COALESCE(SUM(profit_cents), 0) FROM fact_sales",
    "total_paid": "SELECT COALESCE(SUM(amount_cents), 0) FROM fact_payments",
    "balance_owing": "SELECT (SELECT COALESCE(SUM(partner_cut_cents), 0) FROM fact_sales)"
                     " - (SELECT COALESCE(SUM(amount_cents), 0) FROM fact_payments)",
}


class WarehouseMismatch(Exception):
    """The warehouse does not add up to psells' own figures."""


def extract(source):
    """Every row and figure the warehouse is made from, from psells."""
    return {
        "products": psells.all_products(source),
        "in_stock": psells.in_stock_products(source),
        "sales": psells.sales_history(source),
        "returns": psells.returns_history(source),
        "payments": psells.payments_history(source),
        "totals": psells.dashboard_totals(source),
    }


def typed(frame, table):
    """The table's columns, in its order, as its types."""
    columns = TABLES[table]
    return frame.reindex(columns=list(columns)).astype(columns)


def date_dimension(dates):
    """One row for every day from the earliest of dates to the latest."""
    dates = pd.Series(list(dates), dtype="object")
    if dates.empty:
        return typed(pd.DataFrame(), "dim_date")
    days = pd.date_range(dates.min(), dates.max(), freq="D")
    return typed(pd.DataFrame({
        "date": days.date,
        "year": days.year,
        "quarter": days.quarter,
        "month": days.month,
        "month_name": days.month_name(),
        "iso_week": days.isocalendar().week.to_numpy(),
        "day_of_week": days.dayofweek + 1,
        "day_name": days.day_name(),
        "is_weekend": days.dayofweek >= 5,
    }), "dim_date")


def transform(data):
    """The warehouse's tables, from what extract returned."""
    products = pd.DataFrame(data["products"]).rename(columns={"id": "product_id"})
    if not products.empty:
        products["retail_discontinued"] = products["retail_discontinued"] == 1
        # Stored as 0 when discontinued, by the business rules; here "none".
        products["retail_price_cents"] = products["retail_price_cents"].where(
            ~products["retail_discontinued"])
        # psells' answer, not the rule restated here.
        products["in_stock"] = products["product_id"].isin(
            [row["id"] for row in data["in_stock"]])
    sales = pd.DataFrame(data["sales"]).rename(
        columns={"id": "sale_id", "item_id": "product_id"})
    returns = pd.DataFrame(data["returns"]).rename(
        columns={"id": "return_id", "item_id": "product_id"})
    payments = pd.DataFrame(data["payments"]).rename(columns={"id": "payment_id"})

    dates = [row["date"] for kind in ("sales", "returns", "payments")
             for row in data[kind]]
    return {
        "dim_date": date_dimension(dates),
        "dim_product": typed(products, "dim_product"),
        "fact_sales": typed(sales, "fact_sales"),
        "fact_returns": typed(returns, "fact_returns"),
        "fact_payments": typed(payments, "fact_payments"),
    }


def plain(value):
    """A cell as psycopg can send it: None for missing, Python for numpy."""
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return None
    return value.item() if hasattr(value, "item") else value


def copy_frame(connection, table, frame):
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in frame.columns))
    with connection.cursor() as cursor, cursor.copy(statement) as copy:
        for row in frame.itertuples(index=False, name=None):
            copy.write_row([plain(value) for value in row])


def mismatches(warehouse, totals):
    """The names of the dashboard figures the warehouse does not equal."""
    cursor = warehouse.cursor(row_factory=tuple_row)
    return [name for name, query in CHECKS.items()
            if cursor.execute(query).fetchone()[0] != totals[name]]


def load(warehouse, tables, totals, finished_at):
    """Recreate and fill the warehouse in one transaction, and commit only if
    it adds up to totals, psells' own dashboard figures."""
    with warehouse.transaction():
        with open(WAREHOUSE_SQL) as schema:
            warehouse.execute(schema.read())
        for table in TABLES:
            copy_frame(warehouse, table, tables[table])
        different = mismatches(warehouse, totals)
        if different:
            raise WarehouseMismatch(
                "The warehouse does not add up to psells' figures, so it was "
                "not changed: " + ", ".join(different))
        with open(VIEWS_SQL) as views:
            warehouse.execute(views.read())
        warehouse.execute(
            "INSERT INTO etl_run (finished_at, products, sales, returns, "
            "payments) VALUES (%s, %s, %s, %s, %s)",
            (finished_at, len(tables["dim_product"]), len(tables["fact_sales"]),
             len(tables["fact_returns"]), len(tables["fact_payments"])))


def report(tables):
    """What was written, as counts only."""
    return ("Warehouse rebuilt: "
            f"{len(tables['dim_product'])} products, "
            f"{len(tables['fact_sales'])} sales, "
            f"{len(tables['fact_returns'])} returns, "
            f"{len(tables['fact_payments'])} payments, "
            f"{len(tables['dim_date'])} days.")


def main():
    warehouse_url = os.environ.get("PSELLS_WAREHOUSE_URL")
    if not warehouse_url:
        sys.exit("PSELLS_WAREHOUSE_URL is not set. The ETL runs as the etl "
                 "service of compose.analytics.yaml, which sets it.")
    try:
        with psells.connect() as source:
            # One snapshot for every read, and read-only besides the role's.
            with source.transaction():
                source.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                data = extract(source)
        tables = transform(data)
        with psycopg.connect(warehouse_url, autocommit=True) as warehouse:
            load(warehouse, tables, data["totals"], datetime.now(timezone.utc))
    except (psells.DatabaseUnavailable, psycopg.OperationalError,
            WarehouseMismatch) as error:
        sys.exit(str(error))
    print(report(tables))


if __name__ == "__main__":
    main()
