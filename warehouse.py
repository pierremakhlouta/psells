"""Reading the analytics warehouse, for the analytics page.

The warehouse is the second PostgreSQL that analytics/etl.py builds from the
business database; its views, in analytics/views.sql, are the one place the
analysis's figures are worked out. This module only reads them: each function
is one view, in a fixed order, sometimes the first few rows, and nothing is
added, divided or rounded here.

The app reads as psells_reader, which can read those views and nothing else,
at PSELLS_WAREHOUSE_URL. A stack without a warehouse, such as the AWS demo
and the kind cluster for now, leaves it unset, and the page says so.
"""

import os

import psycopg
from psycopg.rows import dict_row


class WarehouseUnavailable(Exception):
    """No warehouse to read, with a sentence the page can show."""


class WarehouseNotSetUp(WarehouseUnavailable):
    """No warehouse is configured here at all, which is not a failure: the
    demo and the cluster have none yet."""


def connect():
    """A read-only connection to the warehouse, as the page reads it.

    Raises WarehouseUnavailable with a sentence when none is set up here, or
    when the one that is does not answer. The sentence never carries the
    address or the driver's message, which can name a host or a user.
    """
    url = os.environ.get("PSELLS_WAREHOUSE_URL", "")
    if not url:
        raise WarehouseNotSetUp(
            "No analytics warehouse is set up here, so there is nothing to "
            "show yet.")
    try:
        return psycopg.connect(url, autocommit=True, row_factory=dict_row,
                               connect_timeout=3)
    except psycopg.OperationalError as error:
        raise WarehouseUnavailable(
            "The analytics warehouse did not answer. Try again in a moment.") \
            from error


def kpis(connection):
    """The headline figures: the one row of kpis."""
    return connection.execute("SELECT * FROM kpis").fetchone()


def sales_by_month(connection):
    """Every month from the first event to the last, oldest first."""
    return connection.execute(
        "SELECT * FROM sales_by_month ORDER BY month").fetchall()


def category_performance(connection):
    """Every category, the highest revenue first; ties by name."""
    return connection.execute(
        "SELECT * FROM category_performance "
        "ORDER BY revenue_cents DESC, category").fetchall()


def top_by_profit(connection, limit=10):
    """The products that made the most profit, by the view's own rank; ties
    by id, so the order is the same every time."""
    return connection.execute(
        "SELECT * FROM product_performance "
        "ORDER BY rank_by_profit, product_id LIMIT %s", (limit,)).fetchall()


def lowest_sell_through(connection, limit=10):
    """The products that sold the smallest share of what came in; among
    equal shares, the most stock first, since more of it is waiting."""
    return connection.execute(
        "SELECT * FROM product_performance "
        "ORDER BY sell_through NULLS LAST, received DESC, product_id LIMIT %s",
        (limit,)).fetchall()
