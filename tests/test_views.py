"""Tests for analytics/views.sql, the warehouse's views.

Invented records go into the test database, the ETL builds the warehouse from
them on the same connection, inside the test's transaction, and each view is
compared with what psells itself answers about the same records. Where a view
works out something psells has no answer for, a margin, a share or a rank,
the test works it out from psells' rows by hand and compares.

The records: four products in three categories, sales in July, September and
October with none in August, a return in August, one payment, one product
never sold, and two products tied on units sold.
"""

import math
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import pytest

import psells
from analytics import etl
from helpers import add_product, add_return, add_sale


FINISHED = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
VIEWS = ("sales_by_month", "sales_by_week", "category_performance",
         "product_performance", "kpis")


@pytest.fixture
def warehouse(db):
    add_product(db, 1, 5)
    add_product(db, 2, 3, retail_discontinued=1, retail_price_cents=0,
                partner_share_mode="custom_amount",
                partner_share_amount_cents=1500, category="Bags")
    add_product(db, 3, 2, partner_share_mode="custom_percent",
                partner_share_percent=25.0)
    add_product(db, 4, 2, category="Watches")
    add_sale(db, 1, 1, 2, sale_price_cents=9000, partner_share_cents=3600,
             date="2026-07-10")
    add_sale(db, 2, 2, 1, sale_price_cents=12000, partner_share_cents=1500,
             date="2026-07-20")
    # A different cut from product 1's first sale, so a margin averaged sale by
    # sale differs from one summed first.
    add_sale(db, 3, 1, 1, sale_price_cents=8500, partner_share_cents=2000,
             date="2026-09-05")
    add_sale(db, 4, 4, 1, sale_price_cents=20000, partner_share_cents=8000,
             date="2026-09-28")
    add_sale(db, 5, 4, 1, sale_price_cents=20000, partner_share_cents=8000,
             date="2026-10-01")
    add_sale(db, 6, 2, 1, sale_price_cents=12000, partner_share_cents=1500,
             date="2026-10-03")
    add_return(db, 1, 1, 1, date="2026-08-15")
    db.execute("INSERT INTO payments (date, amount_cents, notes) "
               "VALUES ('2026-10-02', 5000, 'invented')")

    data = etl.extract(db)
    etl.load(db, etl.transform(data), data["totals"], FINISHED)
    return db


def view(connection, name, order=""):
    return connection.execute(f"SELECT * FROM {name} {order}").fetchall()


def close(ratio, numerator, denominator):
    return math.isclose(float(ratio), numerator / denominator, rel_tol=1e-12)


def sales_by(key, connection):
    """psells' sales, summed by key(sale)."""
    totals = defaultdict(lambda: defaultdict(int))
    for sale in psells.sales_history(connection):
        group = totals[key(sale)]
        group["sales"] += 1
        group["units"] += sale["quantity"]
        group["revenue_cents"] += sale["sale_total_cents"]
        group["partner_cut_cents"] += sale["partner_cut_cents"]
        group["profit_cents"] += sale["profit_cents"]
    return totals


# sales_by_month ----------------------------------------------------------------

def test_every_month_from_first_event_to_last_with_psells_sums(warehouse):
    months = view(warehouse, "sales_by_month", "ORDER BY month")
    expected = sales_by(lambda s: s["date"].replace(day=1), warehouse)

    assert [m["month"] for m in months] == [
        date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]
    for month in months:
        sums = expected.get(month["month"], defaultdict(int))
        for column in ("sales", "units", "revenue_cents", "partner_cut_cents",
                       "profit_cents"):
            assert month[column] == sums[column], (month["month"], column)
    # August had a return and no sale: zeros, and no margin rather than 0%.
    august = months[1]
    assert (august["sales"], august["revenue_cents"], august["margin"]) == (0, 0, None)
    assert (months[0]["month_name"], months[0]["year"], months[0]["month_number"]) == (
        "July", 2026, 7)


def test_monthly_margin_running_total_and_change(warehouse):
    months = view(warehouse, "sales_by_month", "ORDER BY month")
    totals = psells.dashboard_totals(warehouse)

    running = 0
    previous = None
    for month in months:
        running += month["revenue_cents"]
        assert month["cumulative_revenue_cents"] == running
        if previous is None:
            assert month["revenue_change_cents"] is None
        else:
            assert month["revenue_change_cents"] == month["revenue_cents"] - previous
        previous = month["revenue_cents"]
        if month["revenue_cents"]:
            assert close(month["margin"], month["profit_cents"],
                         month["revenue_cents"])
    assert running == totals["total_revenue"]


# sales_by_week -----------------------------------------------------------------

def test_every_iso_week_from_first_event_to_last_with_psells_sums(warehouse):
    weeks = view(warehouse, "sales_by_week", "ORDER BY week_start")
    # Each sale under the Monday that starts its week.
    expected = sales_by(
        lambda s: s["date"] - timedelta(days=s["date"].weekday()), warehouse)

    assert weeks[0]["week_start"] == date(2026, 7, 6)
    assert weeks[-1]["week_start"] == date(2026, 9, 28)
    assert all(w["week_start"].weekday() == 0 for w in weeks)
    assert [w["week_start"] for w in weeks] == sorted(
        {w["week_start"] for w in weeks})
    assert len(weeks) == (weeks[-1]["week_start"] - weeks[0]["week_start"]).days // 7 + 1
    for week in weeks:
        sums = expected.get(week["week_start"], defaultdict(int))
        assert week["revenue_cents"] == sums["revenue_cents"]
        assert week["units"] == sums["units"]
        iso = week["week_start"].isocalendar()
        assert (week["iso_year"], week["iso_week"]) == (iso.year, iso.week)


# category_performance ----------------------------------------------------------

def test_each_category_has_psells_stock_and_money(warehouse):
    categories = {c["category"]: c for c in view(warehouse, "category_performance")}
    stock = defaultdict(lambda: defaultdict(int))
    for product in psells.all_products(warehouse):
        group = stock[product["category"]]
        group["products"] += 1
        for column in ("received", "sold", "returned", "available"):
            group[column] += product[f"quantity_{column}"]
    money = sales_by(lambda s: s["category"], warehouse)

    assert set(categories) == {"Shoes", "Bags", "Watches"}
    for name, category in categories.items():
        for column in ("products", "received", "sold", "returned", "available"):
            assert category[column] == stock[name][column], (name, column)
        for column in ("revenue_cents", "partner_cut_cents", "profit_cents"):
            assert category[column] == money[name][column], (name, column)
        assert close(category["sell_through"], category["sold"], category["received"])


def test_category_margin_is_summed_profit_over_summed_revenue_and_shares_add_up(warehouse):
    categories = {c["category"]: c for c in view(warehouse, "category_performance")}
    total = psells.dashboard_totals(warehouse)["total_revenue"]

    for category in categories.values():
        assert close(category["margin"], category["profit_cents"],
                     category["revenue_cents"]), category["category"]
        assert close(category["revenue_share"], category["revenue_cents"], total)
    assert math.isclose(sum(float(c["revenue_share"]) for c in categories.values()), 1.0)


# product_performance -----------------------------------------------------------

def test_every_product_is_there_sold_or_not(warehouse):
    products = {p["product_id"]: p for p in view(warehouse, "product_performance")}
    psells_products = {p["id"]: p for p in psells.all_products(warehouse)}

    assert set(products) == set(psells_products)
    for product_id, product in products.items():
        assert product["sold"] == psells_products[product_id]["quantity_sold"]
        assert product["available"] == psells_products[product_id]["quantity_available"]
    unsold = products[3]
    assert (unsold["sales"], unsold["revenue_cents"], unsold["margin"]) == (0, 0, None)
    assert unsold["sell_through"] == 0


def test_ranks_share_ties_and_restart_in_each_category(warehouse):
    products = {p["product_id"]: p for p in view(warehouse, "product_performance")}

    # Units sold: 3, 2, 2, 0.
    assert [products[i]["rank_by_units"] for i in (1, 2, 4, 3)] == [1, 2, 2, 4]
    # Revenue: product 4 40000, product 1 26500, product 2 24000, product 3 none.
    assert [products[i]["rank_by_revenue"] for i in (4, 1, 2, 3)] == [1, 2, 3, 4]
    assert products[4]["rank_by_profit"] == 1
    # Within Shoes: product 1 sold, product 3 did not.
    assert (products[1]["rank_in_category_by_profit"],
            products[3]["rank_in_category_by_profit"]) == (1, 2)
    assert products[2]["rank_in_category_by_profit"] == 1


def test_in_stock_is_psells_answer(warehouse):
    in_stock = {p["id"] for p in psells.in_stock_products(warehouse)}
    products = view(warehouse, "product_performance")

    assert {p["product_id"] for p in products if p["in_stock"]} == in_stock
    # Product 4 sold both its units.
    assert 4 not in in_stock


# kpis --------------------------------------------------------------------------

def test_the_headline_figures_are_psells_dashboard(warehouse):
    (kpis,) = view(warehouse, "kpis")
    totals = psells.dashboard_totals(warehouse)

    assert (kpis["received"], kpis["sold"], kpis["returned"], kpis["available"]) == (
        totals["total_received"], totals["total_sold"], totals["total_returned"],
        totals["total_available"])
    assert (kpis["revenue_cents"], kpis["partner_cut_cents"], kpis["profit_cents"],
            kpis["paid_cents"], kpis["balance_owing_cents"]) == (
        totals["total_revenue"], totals["total_partner_share"],
        totals["total_profit"], totals["total_paid"], totals["balance_owing"])
    assert kpis["products"] == len(psells.all_products(warehouse))
    assert kpis["products_in_stock"] == len(psells.in_stock_products(warehouse))
    assert kpis["sales"] == len(psells.sales_history(warehouse))
    assert close(kpis["margin"], totals["total_profit"], totals["total_revenue"])
    assert close(kpis["sell_through"], totals["total_sold"], totals["total_received"])
    assert (kpis["first_sale"], kpis["last_sale"], kpis["built_at"]) == (
        date(2026, 7, 10), date(2026, 10, 3), FINISHED)


def test_an_empty_warehouse_has_one_row_of_kpis_and_no_months(db):
    data = etl.extract(db)
    etl.load(db, etl.transform(data), data["totals"], FINISHED)

    (kpis,) = view(db, "kpis")
    assert (kpis["products"], kpis["revenue_cents"], kpis["margin"],
            kpis["sell_through"]) == (0, 0, None, None)
    for name in ("sales_by_month", "sales_by_week", "category_performance",
                 "product_performance"):
        assert view(db, name) == [], name


# The file ----------------------------------------------------------------------

def test_warehouse_sql_drops_every_view_views_sql_makes():
    folder = os.path.dirname(etl.__file__)
    with open(os.path.join(folder, "views.sql")) as file:
        made = re.findall(r"^CREATE VIEW (\w+)", file.read(), re.M)
    with open(os.path.join(folder, "warehouse.sql")) as file:
        dropped = re.search(r"DROP VIEW IF EXISTS ([^;]+);", file.read()).group(1)

    assert sorted(made) == sorted(VIEWS)
    assert sorted(name.strip() for name in dropped.split(",")) == sorted(made)


def test_a_rebuild_with_the_views_in_place_works(warehouse):
    data = etl.extract(warehouse)
    etl.load(warehouse, etl.transform(data), data["totals"], FINISHED)

    assert len(view(warehouse, "product_performance")) == 4
    assert len(view(warehouse, "sales_by_month")) == 4
    (kpis,) = view(warehouse, "kpis")
    assert kpis["sales"] == 6
