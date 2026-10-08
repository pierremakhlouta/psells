"""Tests for analytics/etl.py, the ETL that builds the warehouse.

Each test builds invented records in the test database, runs extract,
transform and load against that same connection, inside the test's own
transaction, and reads the warehouse's tables back. Every figure is compared
with what psells itself answers: the warehouse may reshape psells' rows but
never work out a figure of its own.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

import psells
from analytics import etl
from helpers import add_product, add_return, add_sale


FINISHED = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def add_payment(connection, amount_cents, on):
    connection.execute(
        "INSERT INTO payments (date, amount_cents, notes) VALUES (%s, %s, %s)",
        (on, amount_cents, "invented"))


@pytest.fixture
def records(db):
    """Three invented products: one on the default share, one discontinued at
    retail on a fixed amount, one never sold; sales, a return and a payment
    spread over a weekend and a month end."""
    add_product(db, 1, 5)
    add_product(db, 2, 3, retail_discontinued=1, retail_price_cents=0,
                partner_share_mode="custom_amount",
                partner_share_amount_cents=1500, category="Bags")
    add_product(db, 3, 2, partner_share_mode="custom_percent",
                partner_share_percent=25.0)
    add_sale(db, 1, 1, 2, sale_price_cents=9000, partner_share_cents=3600,
             date="2026-09-26")
    add_sale(db, 2, 2, 1, sale_price_cents=12000, partner_share_cents=1500,
             date="2026-09-28")
    add_sale(db, 3, 1, 1, sale_price_cents=8500, partner_share_cents=3400,
             date="2026-10-02")
    add_return(db, 1, 1, 1, date="2026-09-30")
    add_payment(db, 5000, "2026-10-01")
    return db


def built(connection):
    """Run the ETL over connection, as source and warehouse both."""
    data = etl.extract(connection)
    tables = etl.transform(data)
    etl.load(connection, tables, data["totals"], FINISHED)
    return tables


def rows(connection, query):
    return connection.execute(query).fetchall()


# What the warehouse holds ------------------------------------------------------

def test_the_warehouse_adds_up_to_psells_own_dashboard(records):
    built(records)
    totals = psells.dashboard_totals(records)

    # The same figures load checked before committing, read back afterwards.
    for name, query in etl.CHECKS.items():
        row = records.execute(query).fetchone()
        assert next(iter(row.values())) == totals[name], name


def test_each_sale_carries_the_figures_psells_works_out_for_it(records):
    built(records)
    expected = {row["id"]: row for row in psells.sales_history(records)}

    for sale in rows(records, "SELECT * FROM fact_sales"):
        source = expected[sale["sale_id"]]
        for column in ("quantity", "sale_price_cents", "partner_share_cents",
                       "sale_total_cents", "partner_cut_cents", "profit_cents"):
            assert sale[column] == source[column], column
        assert (sale["date"], sale["product_id"]) == (source["date"],
                                                      source["item_id"])
    assert len(expected) == 3


def test_each_product_carries_the_stock_psells_works_out_for_it(records):
    built(records)
    expected = {row["id"]: row for row in psells.all_products(records)}

    for product in rows(records, "SELECT * FROM dim_product"):
        source = expected[product["product_id"]]
        for column in ("quantity_received", "quantity_sold",
                       "quantity_returned", "quantity_available",
                       "listed_price_cents", "category", "name"):
            assert product[column] == source[column], column
    assert len(expected) == 3


def test_a_discontinued_products_retail_price_is_none_not_zero(records):
    built(records)
    products = {row["product_id"]: row
                for row in rows(records, "SELECT * FROM dim_product")}

    assert products[2]["retail_discontinued"] is True
    assert products[2]["retail_price_cents"] is None
    assert products[1]["retail_discontinued"] is False
    assert products[1]["retail_price_cents"] == 10000
    # The business database keeps its 0.
    assert psells.all_products(records)[1]["retail_price_cents"] == 0


def test_share_settings_keep_missing_as_missing(records):
    built(records)
    products = {row["product_id"]: row
                for row in rows(records, "SELECT * FROM dim_product")}

    assert products[1]["partner_share_amount_cents"] is None
    assert products[1]["partner_share_percent"] is None
    assert products[2]["partner_share_amount_cents"] == 1500
    assert products[3]["partner_share_percent"] == 25.0


def test_the_date_dimension_covers_every_day_from_first_event_to_last(records):
    built(records)
    days = rows(records, "SELECT * FROM dim_date ORDER BY date")

    assert [d["date"] for d in days] == [
        date(2026, 9, 26) + timedelta(days=n) for n in range(7)]
    saturday = days[0]
    assert (saturday["year"], saturday["quarter"], saturday["month"],
            saturday["month_name"], saturday["iso_week"],
            saturday["day_of_week"], saturday["day_name"],
            saturday["is_weekend"]) == (2026, 3, 9, "September", 39, 6,
                                        "Saturday", True)
    friday = days[-1]
    assert (friday["quarter"], friday["month_name"], friday["day_of_week"],
            friday["is_weekend"]) == (4, "October", 5, False)


def test_notes_never_reach_the_warehouse(records):
    built(records)
    columns = rows(records,
                   "SELECT table_name, column_name FROM information_schema.columns "
                   "WHERE table_name IN ('dim_product', 'fact_returns', "
                   "'fact_payments')")

    assert not [c for c in columns if c["column_name"] == "notes"]


def test_the_run_is_recorded_with_its_counts(records):
    built(records)

    assert rows(records, "SELECT * FROM etl_run") == [{
        "finished_at": FINISHED, "products": 3, "sales": 3, "returns": 1,
        "payments": 1}]


# Rebuilding --------------------------------------------------------------------

def test_running_again_rebuilds_rather_than_adds(records):
    built(records)
    add_sale(records, 4, 3, 1, date="2026-10-03")
    built(records)

    assert len(rows(records, "SELECT * FROM fact_sales")) == 4
    assert len(rows(records, "SELECT * FROM etl_run")) == 1


def test_a_warehouse_that_does_not_add_up_is_refused_and_the_last_one_kept(records):
    built(records)
    data = etl.extract(records)
    add_sale(records, 4, 3, 1, date="2026-10-03")
    tables = etl.transform(etl.extract(records))
    # The rows say four sales; the totals given to load are from three.
    with pytest.raises(etl.WarehouseMismatch) as refused:
        etl.load(records, tables, data["totals"], FINISHED)

    assert "total_sold" in str(refused.value)
    assert "total_revenue" in str(refused.value)
    # No figure in the message: on the Mac it is printed, and they are real.
    assert not any(ch.isdigit() for ch in str(refused.value))
    assert len(rows(records, "SELECT * FROM fact_sales")) == 3


def test_an_empty_database_builds_an_empty_warehouse(db):
    tables = built(db)

    assert all(len(frame) == 0 for frame in tables.values())
    assert rows(db, "SELECT products, sales FROM etl_run") == [
        {"products": 0, "sales": 0}]


# What it prints and how it reads -----------------------------------------------

def test_the_report_gives_counts_and_no_figure(records):
    tables = built(records)

    assert etl.report(tables) == (
        "Warehouse rebuilt: 3 products, 3 sales, 1 returns, 1 payments, 7 days.")


def test_the_etl_reads_through_psells_and_in_one_read_only_snapshot():
    with open(etl.__file__) as file:
        source = file.read()

    for reader in ("all_products", "sales_history", "returns_history",
                   "payments_history", "dashboard_totals"):
        assert f"psells.{reader}(source)" in source
    # No SQL against the business tables of its own.
    assert "FROM sales" not in source and "FROM products" not in source
    assert "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY" in source
    assert source.index("SET TRANSACTION") < source.index("data = extract(source)")
