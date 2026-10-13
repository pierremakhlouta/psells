"""Tests for the analytics page, /analytics, and the percent filter it uses.

The page reads the warehouse through warehouse.connect, which these tests
replace with the test database's own connection after the ETL has built the
warehouse there, inside the test's transaction. Every figure the page shows
is then compared with the view it came from, formatted by the same filters.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

import psells
import warehouse
from analytics import etl
from helpers import add_product, add_sale


@pytest.fixture
def built(db, monkeypatch):
    """The warehouse built from invented records, and the page pointed at it."""
    add_product(db, 1, 4, name="Invented runner")
    add_product(db, 2, 4, category="Bags", name="Invented tote")
    add_product(db, 3, 10, category="Bags", name="Invented satchel")
    add_product(db, 4, 8, category="Hats", name="Invented cap")
    add_sale(db, 1, 1, 3, sale_price_cents=9000, partner_share_cents=3600,
             date="2026-07-10")
    add_sale(db, 2, 2, 1, sale_price_cents=30000, partner_share_cents=5000,
             date="2026-09-20")
    add_sale(db, 3, 4, 2, sale_price_cents=4000, partner_share_cents=1000,
             date="2026-09-21")
    data = etl.extract(db)
    etl.load(db, etl.transform(data), data["totals"],
             datetime(2026, 10, 8, 14, 5, tzinfo=timezone.utc))
    # The page closes what connect gave it; the test's connection stays open.
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(warehouse, "connect", lambda: db)
    return db


def page(client):
    response = client.get("/analytics")
    return response.status_code, response.text


# With a warehouse ---------------------------------------------------------------

def test_the_headline_figures_are_the_kpis_view_formatted(client, built):
    status, html = page(client)
    kpis = built.execute("SELECT * FROM kpis").fetchone()

    assert status == 200
    for figure in (psells.format_cents(kpis["revenue_cents"]),
                   psells.format_cents(kpis["profit_cents"]),
                   psells.format_ratio(kpis["margin"]),
                   psells.format_ratio(kpis["sell_through"]),
                   psells.format_cents(kpis["balance_owing_cents"]),
                   f"{kpis['sold']} of {kpis['received']}",
                   f"{kpis['products_in_stock']} of {kpis['products']}"):
        assert figure in html, figure
    assert "built 8 October 2026, 14:05 UTC" in html


def test_one_bar_per_month_and_series_and_one_per_category(client, built):
    _, html = page(client)
    months = built.execute("SELECT * FROM sales_by_month").fetchall()
    categories = built.execute("SELECT * FROM category_performance").fetchall()

    # July, August with nothing, September.
    assert len(months) == 3
    assert html.count('<rect class="profit"') == len(months)
    assert html.count('<rect class="revenue"') == len(months) + len(categories)
    # Each bar's exact figure is its tooltip.
    for month in months:
        label = month["month"].strftime("%b %Y")
        assert (f"<title>{label}: revenue "
                f"{psells.format_cents(month['revenue_cents'])}</title>") in html
    assert "<title>Aug 2026: revenue $0.00</title>" in html


def test_every_category_row_is_its_view_row_formatted(client, built):
    _, html = page(client)

    for category in built.execute("SELECT * FROM category_performance").fetchall():
        row = (f"<td>{category['category']}</td>")
        assert row in html
        for figure in (psells.format_cents(category["revenue_cents"]),
                       psells.format_ratio(category["margin"]),
                       psells.format_ratio(category["sell_through"]),
                       psells.format_ratio(category["revenue_share"])):
            assert figure in html, (category["category"], figure)


def test_the_product_tables_follow_the_views_order(client, built):
    _, html = page(client)
    top = html[html.index("Most profitable products"):html.index("Lowest sell-through")]
    lowest = html[html.index("Lowest sell-through"):]

    # Profit: tote 25000, runner 16200, cap 6000, satchel nothing.
    names = ["Invented tote", "Invented runner", "Invented cap", "Invented satchel"]
    assert [n for n in sorted(names, key=top.index)] == names
    # Sell-through: satchel 0 of 10, then cap and tote tie at a quarter, the
    # cap with more stock; then the runner, 3 of 4.
    order = ["Invented satchel", "Invented cap", "Invented tote", "Invented runner"]
    assert [n for n in sorted(order, key=lowest.index)] == order


def test_the_page_runs_no_script_and_needs_no_style_attribute(client, built):
    _, html = page(client)

    assert "<svg" in html
    assert "<script" not in html
    assert " style=" not in html


def test_the_page_opens_no_connection_to_the_business_database_of_its_own(client, built):
    # The business connection is the db fixture through the dependency; the
    # page reads only what warehouse.connect gives it, which is also db here,
    # so the proof is that the route takes no Connection.
    import inspect
    import web

    assert list(inspect.signature(web.analytics_page).parameters) == ["request"]


# Without one ---------------------------------------------------------------------

def test_no_warehouse_set_up_is_a_sentence_and_a_200(client, monkeypatch):
    monkeypatch.delenv("PSELLS_WAREHOUSE_URL", raising=False)

    status, html = page(client)
    assert status == 200
    assert "No analytics warehouse is set up here" in html
    assert "<svg" not in html


def test_a_warehouse_that_does_not_answer_is_a_503(client, monkeypatch):
    def refuse():
        raise warehouse.WarehouseUnavailable(
            "The analytics warehouse did not answer. Try again in a moment.")
    monkeypatch.setattr(warehouse, "connect", refuse)

    status, html = page(client)
    assert status == 503
    assert "did not answer" in html


def test_a_warehouse_not_built_yet_is_a_503_with_a_sentence(client, db, monkeypatch):
    # The test database has the business tables and no views at all.
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(warehouse, "connect", lambda: db)

    status, html = page(client)
    assert status == 503
    assert "may not have been built yet" in html
    assert "Traceback" not in html


def test_the_page_needs_a_login(anonymous):
    response = anonymous.get("/analytics", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")


def test_the_nav_links_the_page(client, built):
    _, html = page(client)
    # Its own page, so marked as the one being shown.
    assert 'href="http://testserver/analytics" aria-current="page">Analytics</a>' in html


# The percent filter --------------------------------------------------------------

def test_a_ratio_is_shown_to_one_decimal_half_away_from_zero():
    assert psells.format_ratio(Decimal("0.61234")) == "61.2%"
    assert psells.format_ratio(Decimal("0.61250")) == "61.3%"
    assert psells.format_ratio(0.0005) == "0.1%"
    assert psells.format_ratio(Decimal("-0.0005")) == "-0.1%"
    assert psells.format_ratio(1) == "100.0%"
    assert psells.format_ratio(0) == "0.0%"


def test_nothing_to_divide_by_is_not_a_percentage():
    assert psells.format_ratio(None) == "n/a"


def test_a_stale_warehouse_is_said_on_the_page(client, built):
    built.execute("UPDATE etl_run SET finished_at = now()")
    _, fresh = page(client)
    built.execute("UPDATE etl_run SET finished_at = now() - interval '3 hours'")
    _, stale = page(client)

    warning = "The warehouse was last built more than two hours ago"
    assert warning not in fresh
    assert warning in stale
