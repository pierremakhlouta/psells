import os
import sqlite3

import pytest

import psells


@pytest.fixture
def db():
    """An empty database built from the real schema, held in memory.

    It reads schema.sql itself rather than a copy, so a constraint added there
    is exercised here automatically. Nothing touches the disk and no data files
    are needed, which keeps the suite runnable on a fresh clone and on CI.
    """
    schema_path = os.path.join(os.path.dirname(psells.__file__), "schema.sql")

    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    with open(schema_path) as schema:
        connection.executescript(schema.read())

    connection.row_factory = sqlite3.Row

    return connection


def add_product(connection, product_id, quantity_received, **overrides):
    """Insert one product, so a test only has to state what it cares about."""
    values = {
        "id": product_id,
        "category": "Shoes",
        "name": f"Product {product_id}",
        "quantity_received": quantity_received,
        "retail_price_cents": 10000,
        "listed_price_cents": 9000,
        "retail_discontinued": 0,
        "partner_share_mode": "default",
        "partner_share_percent": None,
        "partner_share_amount_cents": None,
        "condition": "Brand New",
        "notes": "",
    }
    values.update(overrides)

    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)

    connection.execute(
        f"INSERT INTO products ({columns}) VALUES ({placeholders})",
        tuple(values.values())
    )


def add_sale(connection, sale_id, item_id, quantity, sale_price_cents=9000,
             partner_share_cents=3500):
    connection.execute(
        "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)",
        (sale_id, "2026-09-01", item_id, quantity,
         sale_price_cents, partner_share_cents)
    )


def add_return(connection, return_id, item_id, quantity):
    connection.execute(
        "INSERT INTO returns VALUES (?, ?, ?, ?, ?)",
        (return_id, "2026-09-01", item_id, quantity, "")
    )


def stock(connection, product_id):
    """The three derived quantities for one product, from the view."""
    return connection.execute(
        "SELECT quantity_sold, quantity_returned, quantity_available "
        "FROM products_view WHERE id = ?",
        (product_id,)
    ).fetchone()


def test_view_counts_down_from_sales(db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=4)

    row = stock(db, 1)

    assert row["quantity_sold"] == 4
    assert row["quantity_available"] == 6


def test_view_with_nothing_sold(db):
    add_product(db, 1, quantity_received=5)

    row = stock(db, 1)

    assert row["quantity_sold"] == 0
    assert row["quantity_available"] == 5


def test_view_when_sold_out(db):
    add_product(db, 1, quantity_received=3)
    add_sale(db, 1, item_id=1, quantity=3)

    assert stock(db, 1)["quantity_available"] == 0


def test_view_subtracts_returns_as_well_as_sales(db):
    """The case the old Python helper could not express at all."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)
    add_return(db, 1, item_id=1, quantity=2)

    row = stock(db, 1)

    assert row["quantity_sold"] == 3
    assert row["quantity_returned"] == 2
    assert row["quantity_available"] == 5


def test_view_does_not_multiply_sales_by_returns(db):
    """Two sales and three returns must not become six rows.

    Joining both tables to products at once would do exactly that, and both
    sums would come out wrong. The view aggregates each table separately first.
    """
    add_product(db, 1, quantity_received=20)
    add_sale(db, 1, item_id=1, quantity=1)
    add_sale(db, 2, item_id=1, quantity=2)
    add_return(db, 1, item_id=1, quantity=1)
    add_return(db, 2, item_id=1, quantity=1)
    add_return(db, 3, item_id=1, quantity=1)

    row = stock(db, 1)

    assert row["quantity_sold"] == 3
    assert row["quantity_returned"] == 3
    assert row["quantity_available"] == 14


def test_view_keeps_products_that_have_never_sold(db):
    """Most of the real inventory has never sold.

    A plain JOIN instead of a LEFT JOIN would drop every one of them from the
    view, silently, and the inventory listing would lose most of its rows.
    """
    add_product(db, 1, quantity_received=5)
    add_product(db, 2, quantity_received=7)
    add_sale(db, 1, item_id=1, quantity=1)

    ids = [r["id"] for r in db.execute("SELECT id FROM products_view ORDER BY id")]

    assert ids == [1, 2]
    assert stock(db, 2)["quantity_available"] == 7


@pytest.fixture
def inventory():
    return [
        {"id": 1, "name": "Nike Air Max 90"},
        {"id": 2, "name": "Nike Air Force 1"},
        {"id": 3, "name": "Adidas Samba"}
    ]


def test_find_items_by_name_exact_name(inventory):
    matches = psells.find_items_by_name(inventory, "Adidas Samba")

    assert [item["id"] for item in matches] == [3]


def test_find_items_by_name_is_case_insensitive(inventory):
    lower = psells.find_items_by_name(inventory, "adidas samba")
    upper = psells.find_items_by_name(inventory, "ADIDAS SAMBA")

    assert [item["id"] for item in lower] == [3]
    assert [item["id"] for item in upper] == [3]


def test_find_items_by_name_matches_a_substring(inventory):
    matches = psells.find_items_by_name(inventory, "force")

    assert [item["id"] for item in matches] == [2]


def test_find_items_by_name_returns_every_match(inventory):
    matches = psells.find_items_by_name(inventory, "nike")

    assert [item["id"] for item in matches] == [1, 2]


def test_find_items_by_name_returns_empty_list_when_nothing_matches(inventory):
    assert psells.find_items_by_name(inventory, "Puma") == []

def test_partner_share_default_mode(monkeypatch):
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 40.0)

    item = {
        "partner_share_mode": "default",
        "retail_price_cents": 50000
    }

    assert psells.partner_share_for(item) == 20000


def test_partner_share_rounds_a_fraction_of_a_cent(monkeypatch):
    """40 percent of 19.99 is 799.6 cents, which is not a payable amount."""
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 40.0)

    item = {
        "partner_share_mode": "default",
        "retail_price_cents": 1999
    }

    assert psells.partner_share_for(item) == 800


def test_partner_share_rounds_half_away_from_zero(monkeypatch):
    """5 percent of 10 cents is exactly half a cent.

    Python's built-in round() would give 0 here, because it rounds half to the
    nearest even number. Money is settled between two people, so it rounds up.
    """
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 5.0)

    item = {
        "partner_share_mode": "default",
        "retail_price_cents": 10
    }

    assert psells.partner_share_for(item) == 1


def test_partner_share_custom_percent_mode():
    item = {
        "partner_share_mode": "custom_percent",
        "retail_price_cents": 70000,
        "partner_share_percent": 40.0
    }

    assert psells.partner_share_for(item) == 28000


def test_partner_share_custom_amount_mode_ignores_retail_price():
    item = {
        "partner_share_mode": "custom_amount",
        "retail_price_cents": 70000,
        "partner_share_amount_cents": 3000
    }

    assert psells.partner_share_for(item) == 3000


def test_partner_share_for_a_discontinued_item():
    item = {
        "partner_share_mode": "custom_amount",
        "retail_price_cents": 0,
        "partner_share_amount_cents": 2500
    }

    assert psells.partner_share_for(item) == 2500


def test_partner_share_unknown_mode_raises():
    item = {
        "partner_share_mode": "percentage",
        "retail_price_cents": 10000
    }

    with pytest.raises(ValueError, match="Invalid partner share mode"):
        psells.partner_share_for(item)

def test_a_product_with_sales_cannot_be_deleted(db):
    """I1, the issue this phase was meant to close.

    Deleting a product used to leave its sales pointing at nothing. The foreign
    key now refuses it outright, which is what makes the rule a guarantee rather
    than something the application has to remember.
    """
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=1)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM products WHERE id = 1")


def test_a_product_with_returns_cannot_be_deleted(db):
    add_product(db, 1, quantity_received=5)
    add_return(db, 1, item_id=1, quantity=1)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM products WHERE id = 1")


def test_a_product_with_no_transactions_can_be_deleted(db):
    """Blocking must not mean nothing is ever deletable.

    Most products have never sold, and correcting a mistyped one has to stay
    possible.
    """
    add_product(db, 1, quantity_received=5)

    db.execute("DELETE FROM products WHERE id = 1")

    assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0


@pytest.fixture
def totals(db):
    """Two products, three sales, one return, two payments.

    Every figure below was worked out by hand so the tests check arithmetic
    rather than agree with whatever the code happens to produce.

        received   5 + 10                      = 15
        sold       2 + 3 + 1                   = 6
        returned   1                           = 1
        available  15 - 6 - 1                  = 8
        revenue    2*15000 + 3*8000 + 1*1999   = 55999
        partner    2*7000  + 3*2500 + 1*800    = 22300
        profit     55999 - 22300               = 33699
        paid       10000 + 5000                = 15000
        owing      22300 - 15000               = 7300
    """
    add_product(db, 1, quantity_received=5)
    add_product(db, 2, quantity_received=10)

    add_sale(db, 1, item_id=1, quantity=2,
             sale_price_cents=15000, partner_share_cents=7000)
    add_sale(db, 2, item_id=2, quantity=3,
             sale_price_cents=8000, partner_share_cents=2500)
    add_sale(db, 3, item_id=2, quantity=1,
             sale_price_cents=1999, partner_share_cents=800)

    add_return(db, 1, item_id=1, quantity=1)

    db.execute("INSERT INTO payments VALUES (1, '2026-09-01', 10000, '')")
    db.execute("INSERT INTO payments VALUES (2, '2026-09-02', 5000, '')")

    return psells.dashboard_totals(db)


def test_dashboard_quantities(totals):
    assert totals["total_received"] == 15
    assert totals["total_sold"] == 6
    assert totals["total_available"] == 8
    assert totals["total_returned"] == 1


def test_dashboard_revenue(totals):
    assert totals["total_revenue"] == 55999


def test_dashboard_partner_share_earned(totals):
    assert totals["total_partner_share"] == 22300


def test_dashboard_profit(totals):
    assert totals["total_profit"] == 33699


def test_dashboard_total_paid(totals):
    assert totals["total_paid"] == 15000


def test_dashboard_balance_owing(totals):
    assert totals["balance_owing"] == 7300


def test_dashboard_on_an_empty_database(db):
    """SUM over no rows is NULL, not zero.

    Without COALESCE in every one of those queries, this raises rather than
    returning zeros, and it would do so on a fresh database with no returns
    recorded, which is the state the real one was in after the migration.
    """
    empty = psells.dashboard_totals(db)

    assert empty["total_received"] == 0
    assert empty["total_returned"] == 0
    assert empty["total_revenue"] == 0
    assert empty["total_available"] == 0
    assert empty["balance_owing"] == 0
