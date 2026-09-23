import os
import sqlite3

import pytest

import psells

from helpers import add_product, add_return, add_sale, stock


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

@pytest.fixture
def catalogue():
    return [
        {"id": 1, "name": "Nike Air Max 90", "category": "Shoes"},
        {"id": 2, "name": "Ray-Ban Aviator", "category": "Glasses"},
        {"id": 3, "name": "Reading Glasses", "category": "Accessories"},
    ]


def test_search_matches_a_category(catalogue):
    matches = psells.find_items_by_name_or_category(catalogue, "glasses")

    assert sorted(item["id"] for item in matches) == [2, 3]


def test_search_matches_a_name(catalogue):
    matches = psells.find_items_by_name_or_category(catalogue, "aviator")

    assert [item["id"] for item in matches] == [2]


def test_search_lists_a_product_once_when_both_match(catalogue):
    """Item 2 matches "glass" by category and item 3 by name.

    Neither should appear twice, and a term hitting both fields on the same
    product must not duplicate it either.
    """
    matches = psells.find_items_by_name_or_category(catalogue, "glass")
    ids = [item["id"] for item in matches]

    assert sorted(ids) == [2, 3]
    assert len(ids) == len(set(ids))


def test_search_with_no_match_returns_an_empty_list(catalogue):
    assert psells.find_items_by_name_or_category(catalogue, "kettle") == []


def test_choosing_a_product_still_matches_on_name_only(catalogue):
    """The deliberate asymmetry, locked down.

    Browsing matches category. Choosing a product to sell, edit or delete does
    not, because that would list an entire category and then act on whichever
    id was typed. Widening this later should be a decision, not an accident.
    """
    assert psells.find_items_by_name(catalogue, "glasses") == [catalogue[2]]


def test_category_counts_lists_each_category_once(db):
    add_product(db, 1, quantity_received=1, category="Watches")
    add_product(db, 2, quantity_received=1, category="Watches")
    add_product(db, 3, quantity_received=1, category="Bags")

    rows = psells.category_counts(db)

    assert [(r["category"], r["products"]) for r in rows] == [
        ("Bags", 1),
        ("Watches", 2),
    ]


def test_category_counts_is_alphabetical(db):
    for i, category in enumerate(["Watches", "Bags", "Shoes"], start=1):
        add_product(db, i, quantity_received=1, category=category)

    assert [r["category"] for r in psells.category_counts(db)] == [
        "Bags", "Shoes", "Watches"
    ]


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


# create_sale -----------------------------------------------------------------
#
# The whole of recording a sale with none of the asking. record_sale drives it
# from a keyboard and the API drives it from a request body, so the rules below
# are the only thing standing between a bad request and a bad row. Several of
# these cannot happen through the CLI at all, because a prompt refuses them
# first, and those are exactly the ones worth having.

def sale_count(connection):
    return connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0]


def test_create_sale_stores_the_row_and_returns_the_cut(db, partner_rate):
    add_product(db, 1, quantity_received=10)

    partner_cut = psells.create_sale(db, 1, 2, 8999, "2026-09-14")

    sale = db.execute("SELECT * FROM sales").fetchone()

    assert partner_cut == 4000
    assert sale["item_id"] == 1
    assert sale["quantity"] == 2
    assert sale["sale_price_cents"] == 8999
    assert sale["partner_share_cents"] == 4000
    assert sale["date"] == "2026-09-14"
    assert stock(db, 1)["quantity_available"] == 8


def test_create_sale_refuses_an_unknown_product(db, partner_rate):
    with pytest.raises(psells.SaleError, match="No product with id 99"):
        psells.create_sale(db, 99, 1, 100, "2026-09-14")

    assert sale_count(db) == 0


def test_create_sale_refuses_a_quantity_below_one(db, partner_rate):
    add_product(db, 1, quantity_received=10)

    with pytest.raises(psells.SaleError, match="at least 1"):
        psells.create_sale(db, 1, 0, 100, "2026-09-14")

    assert sale_count(db) == 0


def test_create_sale_refuses_more_than_is_available(db, partner_rate):
    add_product(db, 1, quantity_received=3)

    with pytest.raises(psells.SaleError, match="Only 3 available"):
        psells.create_sale(db, 1, 4, 100, "2026-09-14")

    assert sale_count(db) == 0


def test_create_sale_refuses_a_sold_out_product(db, partner_rate):
    add_product(db, 1, quantity_received=2)
    add_sale(db, 1, item_id=1, quantity=2)

    with pytest.raises(psells.SaleError, match="no stock available"):
        psells.create_sale(db, 1, 1, 100, "2026-09-14")

    assert sale_count(db) == 1


def test_create_sale_refuses_a_negative_price(db, partner_rate):
    add_product(db, 1, quantity_received=10)

    with pytest.raises(psells.SaleError, match="cannot be negative"):
        psells.create_sale(db, 1, 1, -100, "2026-09-14")

    assert sale_count(db) == 0


def test_create_sale_refuses_a_date_that_does_not_exist(db, partner_rate):
    """The schema refuses this too, but not with a sentence anyone can act on.

    Caught here so the caller gets a message about its input rather than a
    constraint failure, which an API would otherwise report as a server error.
    """
    add_product(db, 1, quantity_received=10)

    with pytest.raises(psells.SaleError, match="not a date"):
        psells.create_sale(db, 1, 1, 100, "2026-02-30")

    assert sale_count(db) == 0


def test_create_sale_stores_a_date_in_the_form_the_schema_requires(
        db, partner_rate):
    """strptime reads 2026-9-3, and the schema's date check accepts only
    2026-09-03. Refusing it with a constraint error would be wrong: it is a
    real date. It is written back zero-padded, as ask_date does."""
    add_product(db, 1, quantity_received=5)

    psells.create_sale(db, 1, 1, 9000, "2026-9-3")

    assert db.execute("SELECT date FROM sales").fetchone()[0] == "2026-09-03"


def test_create_sale_freezes_the_cut_at_the_moment_of_sale(db, partner_rate,
                                                           monkeypatch):
    add_product(db, 1, quantity_received=10)

    psells.create_sale(db, 1, 1, 8999, "2026-09-14")

    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 10.0)

    assert psells.create_sale(db, 1, 1, 8999, "2026-09-15") == 1000
    # A row is a sqlite3.Row, not a tuple, so read the column out of each.
    stored = [
        row["partner_share_cents"]
        for row in db.execute(
            "SELECT partner_share_cents FROM sales ORDER BY id"
        )
    ]

    assert stored == [4000, 1000]


# The whole of adding a product with none of the asking. add drives it from a
# keyboard and the web form will drive it from a request, so every rule is
# tested here once, directly, rather than through either of them.

def new_product(**overrides):
    """Arguments for an acceptable product on the default share."""
    values = {
        "category": "Shoes",
        "name": "Jordan 1 Chicago",
        "quantity_received": 10,
        "retail_discontinued": False,
        "retail_price_cents": 10000,
        "listed_price_cents": 9000,
        "condition": "Brand New",
        "notes": "boxed",
        "partner_share_mode": "default",
        "partner_share_percent": None,
        "partner_share_amount_cents": None,
    }
    values.update(overrides)

    return values


def refusal(db, **overrides):
    """The problems create_product raises, having checked nothing was stored."""
    with pytest.raises(psells.ProductError) as refused:
        psells.create_product(db, **new_product(**overrides))

    assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0

    return refused.value.problems


def test_create_product_stores_every_field_and_returns_the_id(db):
    product_id = psells.create_product(db, **new_product())

    stored = dict(db.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone())

    assert stored == {
        "id": product_id,
        "category": "Shoes",
        "name": "Jordan 1 Chicago",
        "quantity_received": 10,
        "retail_price_cents": 10000,
        "listed_price_cents": 9000,
        "retail_discontinued": 0,
        "partner_share_mode": "default",
        "partner_share_percent": None,
        "partner_share_amount_cents": None,
        "condition": "Brand New",
        "notes": "boxed",
    }


def test_create_product_lets_sqlite_choose_the_id(db):
    first = psells.create_product(db, **new_product())
    second = psells.create_product(db, **new_product(name="Jordan 4 Bred"))

    assert second == first + 1


def test_create_product_strips_the_text_it_stores(db):
    product_id = psells.create_product(db, **new_product(
        category="  Shoes ", name=" Jordan 1 ", condition=" Used ",
        notes="  boxed  ",
    ))

    stored = db.execute(
        "SELECT category, name, condition, notes FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()

    assert tuple(stored) == ("Shoes", "Jordan 1", "Used", "boxed")


def test_create_product_stores_a_custom_percentage(db):
    product_id = psells.create_product(db, **new_product(
        partner_share_mode="custom_percent", partner_share_percent=35.5,
    ))

    stored = db.execute(
        "SELECT partner_share_percent, partner_share_amount_cents "
        "FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    assert tuple(stored) == (35.5, None)


def test_create_product_stores_a_discontinued_product(db):
    product_id = psells.create_product(db, **new_product(
        retail_discontinued=True, retail_price_cents=0,
        partner_share_mode="custom_amount", partner_share_amount_cents=1250,
    ))

    stored = db.execute(
        "SELECT retail_discontinued, retail_price_cents, "
        "partner_share_mode, partner_share_amount_cents "
        "FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    assert tuple(stored) == (1, 0, "custom_amount", 1250)


def test_create_product_reports_every_problem_at_once(db):
    """Seven things wrong, seven sentences, one refusal, nothing stored."""
    problems = refusal(
        db,
        category=" ", name="", quantity_received=0, retail_price_cents=0,
        listed_price_cents=-1, condition="", partner_share_mode="bogus",
    )

    assert set(problems) == {
        "category", "name", "quantity_received", "retail_price",
        "listed_price", "condition", "partner_share_mode",
    }
    assert problems["category"] == "Category cannot be blank."


def test_a_product_error_is_a_value_error_that_reads_as_a_sentence(db):
    with pytest.raises(ValueError) as refused:
        psells.create_product(db, **new_product(name="", condition=""))

    assert str(refused.value) == (
        "Name cannot be blank. Condition cannot be blank."
    )


def test_a_quantity_must_be_a_whole_number_of_at_least_one(db):
    assert "quantity_received" in refusal(db, quantity_received=0)
    assert "quantity_received" in refusal(db, quantity_received=2.5)
    assert "quantity_received" in refusal(db, quantity_received=True)

    assert psells.create_product(db, **new_product(quantity_received=1))


def test_a_retail_price_must_be_at_least_one_cent(db):
    """Zero is reserved for products discontinued at retail."""
    assert refusal(db, retail_price_cents=0)["retail_price"] == (
        "Retail price must be at least $0.01."
    )

    assert psells.create_product(db, **new_product(retail_price_cents=1))


def test_a_listed_price_of_zero_is_allowed(db):
    assert psells.create_product(db, **new_product(listed_price_cents=0))


def test_a_discontinued_product_cannot_have_a_retail_price(db):
    problems = refusal(
        db, retail_discontinued=True, retail_price_cents=5000,
        partner_share_mode="custom_amount", partner_share_amount_cents=100,
    )

    assert set(problems) == {"retail_price"}


def test_a_discontinued_product_must_take_a_fixed_amount(db):
    problems = refusal(db, retail_discontinued=True, retail_price_cents=0)

    assert set(problems) == {"partner_share_mode"}


@pytest.mark.parametrize("percent", [-1, 100.5, float("nan"), float("inf"),
                                     True, None, "35"])
def test_a_percentage_outside_nought_to_a_hundred_is_refused(db, percent):
    """nan and infinity included: float() accepts both from text."""
    problems = refusal(db, partner_share_mode="custom_percent",
                       partner_share_percent=percent)

    assert set(problems) == {"partner_share_percent"}


@pytest.mark.parametrize("percent", [0, 100, 12.5])
def test_a_percentage_from_nought_to_a_hundred_is_accepted(db, percent):
    assert psells.create_product(db, **new_product(
        partner_share_mode="custom_percent", partner_share_percent=percent,
    ))


def test_a_fixed_amount_cannot_be_negative_but_can_be_zero(db):
    """Zero is accepted on purpose: open issue I9, still intentional."""
    problems = refusal(db, partner_share_mode="custom_amount",
                       partner_share_amount_cents=-1)

    assert set(problems) == {"partner_share_amount"}
    assert psells.create_product(db, **new_product(
        partner_share_mode="custom_amount", partner_share_amount_cents=0,
    ))


def test_a_mode_carries_only_its_own_value(db):
    """The shape the matrix constraint requires, refused in a sentence first."""
    assert set(refusal(db, partner_share_percent=40)) == {
        "partner_share_percent"}
    assert set(refusal(db, partner_share_amount_cents=500)) == {
        "partner_share_amount"}
    assert set(refusal(db, partner_share_mode="custom_percent",
                       partner_share_percent=40,
                       partner_share_amount_cents=500)) == {
        "partner_share_amount"}


def test_a_field_that_could_not_be_read_is_required(db):
    """None is what a caller parsing text passes for a field it could not
    read. product_problems skips it, create_product refuses it."""
    problems = refusal(db, name=None, listed_price_cents=None)

    assert problems == {
        "name": "This field is required.",
        "listed_price": "This field is required.",
    }
    assert psells.product_problems(**{
        k: v for k, v in new_product(name=None).items() if k != "notes"
    }) == {}


# The whole of editing a product with none of the asking. Every field is
# given; the rules are create_product's plus the intake floor.

def stored_product(db, product_id=1):
    return dict(db.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone())


def edit_refusal(db, product_id=1, **overrides):
    """The problems update_product raises, having checked nothing changed."""
    before = stored_product(db, product_id)

    with pytest.raises(psells.ProductError) as refused:
        psells.update_product(db, product_id, **new_product(**overrides))

    assert stored_product(db, product_id) == before

    return refused.value.problems


def test_update_product_replaces_every_field(db):
    add_product(db, 1, quantity_received=5, name="Old name", notes="old")

    psells.update_product(db, 1, **new_product(
        category="Hats", name="New name", quantity_received=8,
        retail_price_cents=5000, listed_price_cents=4500, condition="Used",
        notes="new", partner_share_mode="custom_percent",
        partner_share_percent=30.0,
    ))

    assert stored_product(db) == {
        "id": 1, "category": "Hats", "name": "New name",
        "quantity_received": 8, "retail_price_cents": 5000,
        "listed_price_cents": 4500, "retail_discontinued": 0,
        "partner_share_mode": "custom_percent", "partner_share_percent": 30.0,
        "partner_share_amount_cents": None, "condition": "Used",
        "notes": "new",
    }


def test_update_product_leaves_other_products_alone(db):
    add_product(db, 1, quantity_received=5)
    add_product(db, 2, quantity_received=5, name="Untouched")
    before = stored_product(db, 2)

    psells.update_product(db, 1, **new_product(name="Changed"))

    assert stored_product(db, 2) == before


def test_notes_can_be_cleared(db):
    """Blank means cleared, which is what a form showing the notes means.
    The command line's edit still cannot do this: open issue I8."""
    add_product(db, 1, quantity_received=5, notes="boxed")

    psells.update_product(db, 1, **new_product(notes=""))

    assert stored_product(db)["notes"] == ""


def test_update_product_is_held_to_the_same_rules_as_create(db):
    add_product(db, 1, quantity_received=5)

    problems = edit_refusal(db, name="", listed_price_cents=-1,
                            partner_share_mode="bogus")

    assert set(problems) == {"name", "listed_price", "partner_share_mode"}


def test_the_intake_cannot_fall_below_what_has_already_gone(db):
    """Four sold and one returned: five units have left the intake."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=4)
    add_return(db, 1, item_id=1, quantity=1)

    assert edit_refusal(db, quantity_received=4) == {
        "quantity_received": "Quantity received cannot be less than 5, the "
                             "units already sold or returned.",
    }

    psells.update_product(db, 1, **new_product(quantity_received=5))

    assert stored_product(db)["quantity_received"] == 5


def test_the_intake_floor_is_still_one_when_nothing_has_gone(db):
    add_product(db, 1, quantity_received=10)

    assert set(edit_refusal(db, quantity_received=0)) == {"quantity_received"}


def test_going_discontinued_needs_a_fixed_amount(db):
    add_product(db, 1, quantity_received=5)

    assert set(edit_refusal(db, retail_discontinued=True,
                            retail_price_cents=0)) == {"partner_share_mode"}

    psells.update_product(db, 1, **new_product(
        retail_discontinued=True, retail_price_cents=0,
        partner_share_mode="custom_amount", partner_share_amount_cents=700,
    ))

    assert stored_product(db)["retail_discontinued"] == 1


def test_coming_back_to_retail_needs_a_retail_price(db):
    add_product(db, 1, quantity_received=5, retail_price_cents=0,
                retail_discontinued=1, partner_share_mode="custom_amount",
                partner_share_amount_cents=700)

    assert set(edit_refusal(db, retail_price_cents=0)) == {"retail_price"}


def test_an_edit_never_rewrites_a_sale(db):
    """The cut frozen onto a sale stays, and so does every dashboard figure
    built from sales, whatever the product's partner share becomes."""
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=2, sale_price_cents=9000,
             partner_share_cents=3500)
    sale_before = dict(db.execute("SELECT * FROM sales").fetchone())
    totals_before = psells.dashboard_totals(db)

    psells.update_product(db, 1, **new_product(
        quantity_received=5, partner_share_mode="custom_amount",
        partner_share_amount_cents=100, listed_price_cents=1,
    ))

    assert dict(db.execute("SELECT * FROM sales").fetchone()) == sale_before
    assert psells.dashboard_totals(db) == totals_before


def test_editing_a_product_that_does_not_exist(db):
    with pytest.raises(psells.ProductNotFound):
        psells.update_product(db, 99, **new_product())


def test_update_product_strips_the_text_it_stores(db):
    add_product(db, 1, quantity_received=5)

    psells.update_product(db, 1, **new_product(name="  Spaced  ",
                                                notes=" n "))

    assert stored_product(db)["name"] == "Spaced"
    assert stored_product(db)["notes"] == "n"


# A product from a form's text. Everything arrives as a string, and a field
# left empty arrives as "". These test the reading; the rules themselves are
# create_product's, tested above.

def form_text(**overrides):
    """A form as a browser sends it, for an acceptable default-share product."""
    fields = {
        "category": "Shoes",
        "name": "Jordan 1 Chicago",
        "quantity_received": "10",
        "retail_discontinued": "",
        "retail_price": "100.00",
        "listed_price": "90.00",
        "condition": "Brand New",
        "notes": "",
        "partner_share_mode": "default",
        "partner_share_percent": "",
        "partner_share_amount": "",
    }
    fields.update(overrides)

    return fields


def text_refusal(db, **overrides):
    with pytest.raises(psells.ProductError) as refused:
        psells.create_product_from_text(db, form_text(**overrides))

    assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0

    return refused.value.problems


def test_a_product_is_read_from_text_and_stored_in_cents(db):
    product_id = psells.create_product_from_text(db, form_text())

    stored = db.execute(
        "SELECT quantity_received, retail_price_cents, listed_price_cents "
        "FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    assert tuple(stored) == (10, 10000, 9000)


def test_every_field_left_empty_is_reported_at_once(db):
    problems = text_refusal(db, **{key: "" for key in form_text()})

    assert problems == {
        "category": "Category cannot be blank.",
        "name": "Name cannot be blank.",
        "condition": "Condition cannot be blank.",
        "quantity_received": "This field is required.",
        "retail_price": "This field is required.",
        "listed_price": "This field is required.",
        "partner_share_mode": "This field is required.",
    }


def test_spaces_alone_count_as_empty(db):
    problems = text_refusal(db, name="   ", quantity_received="  ")

    assert problems["name"] == "Name cannot be blank."
    assert problems["quantity_received"] == "This field is required."


def test_money_that_is_not_an_amount_gets_the_command_lines_sentence(db):
    problems = text_refusal(db, listed_price="9O.00", retail_price="12.345")

    assert problems == {
        "listed_price": psells.MONEY_TEXT_PROBLEM,
        "retail_price": psells.MONEY_TEXT_PROBLEM,
    }


def test_a_quantity_must_be_written_as_a_whole_number(db):
    assert text_refusal(db, quantity_received="2.5") == {
        "quantity_received":
            "Quantity received must be a whole number, at least 1.",
    }


def test_what_cannot_be_read_and_what_breaks_a_rule_come_together(db):
    """A blank name is a rule; a price of abc cannot be read. One refusal."""
    problems = text_refusal(db, name="", listed_price="abc",
                            quantity_received="0")

    assert set(problems) == {"name", "listed_price", "quantity_received"}


def test_the_discontinued_box_is_ticked_or_not_and_nothing_else(db):
    assert set(text_refusal(db, retail_discontinued="maybe")) == {
        "retail_discontinued"}


def test_a_discontinued_product_ignores_the_retail_price_typed(db):
    """Zero by definition, and the command line never asks for it."""
    product_id = psells.create_product_from_text(db, form_text(
        retail_discontinued="yes", retail_price="100.00",
        partner_share_mode="custom_amount", partner_share_amount="12.50",
    ))

    stored = db.execute(
        "SELECT retail_discontinued, retail_price_cents, "
        "partner_share_amount_cents FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    assert tuple(stored) == (1, 0, 1250)


def test_a_value_for_a_mode_not_chosen_is_ignored(db):
    product_id = psells.create_product_from_text(db, form_text(
        partner_share_percent="35", partner_share_amount="5.00",
    ))

    stored = db.execute(
        "SELECT partner_share_percent, partner_share_amount_cents "
        "FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    assert tuple(stored) == (None, None)


def test_the_chosen_modes_value_is_required(db):
    assert text_refusal(db, partner_share_mode="custom_percent") == {
        "partner_share_percent": "This field is required."}
    assert text_refusal(db, partner_share_mode="custom_amount") == {
        "partner_share_amount": "This field is required."}


@pytest.mark.parametrize("text", ["abc", "nan", "inf", "150", "-1"])
def test_a_percentage_typed_badly_is_refused(db, text):
    problems = text_refusal(db, partner_share_mode="custom_percent",
                            partner_share_percent=text)

    assert problems == {"partner_share_percent":
                        "Partner share percentage must be a number from 0 to 100."}


def test_a_fixed_amount_is_read_as_money(db):
    assert text_refusal(db, partner_share_mode="custom_amount",
                        partner_share_amount="12.5.0") == {
        "partner_share_amount": psells.MONEY_TEXT_PROBLEM}


# An edit form's text, both ways.

@pytest.mark.parametrize("overrides", [
    {},
    {"partner_share_mode": "custom_percent", "partner_share_percent": 33.333333},
    {"partner_share_mode": "custom_percent", "partner_share_percent": 0.1},
    {"partner_share_mode": "custom_amount", "partner_share_amount_cents": 1},
    {"retail_discontinued": 1, "retail_price_cents": 0,
     "partner_share_mode": "custom_amount", "partner_share_amount_cents": 0},
    {"listed_price_cents": 0, "notes": ""},
])
def test_a_products_form_text_reads_back_as_the_product(db, overrides):
    """Opening the edit form and saving it unchanged must change nothing."""
    add_product(db, 1, quantity_received=10, **overrides)
    product = psells.all_products(db)[0]

    values, problems = psells.read_product_text(
        psells.product_form_text(product))

    assert problems == {}
    assert values == {
        key: bool(product[key]) if key == "retail_discontinued" else product[key]
        for key in values
    }


def test_update_product_from_text_reports_the_floor_with_the_rest(db):
    """A price that cannot be read, a blank name and a quantity below what
    has gone: all three in one refusal."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=6)

    with pytest.raises(psells.ProductError) as refused:
        psells.update_product_from_text(db, 1, form_text(
            name="", listed_price="abc", quantity_received="3"))

    assert set(refused.value.problems) == {"name", "listed_price",
                                           "quantity_received"}


def test_update_product_from_text_for_a_missing_product(db):
    with pytest.raises(psells.ProductNotFound):
        psells.update_product_from_text(db, 99, form_text(listed_price="x"))


# A sale from a form's text.

def test_a_sale_is_read_from_text(db, partner_rate):
    add_product(db, 1, quantity_received=5)

    cut = psells.create_sale_from_text(
        db, 1, {"quantity": " 2 ", "sale_price": "85.50", "date": "2026-9-3"})

    stored = db.execute("SELECT quantity, sale_price_cents, date, "
                        "partner_share_cents FROM sales").fetchone()

    assert tuple(stored) == (2, 8550, "2026-09-03", 4000)
    assert cut == 4000


def test_every_sale_field_left_empty_is_reported_at_once(db):
    """A blank date is not a problem: it means today."""
    with pytest.raises(psells.SaleInputError) as refused:
        psells.create_sale_from_text(db, 1, {})

    assert refused.value.problems == {
        "quantity": "This field is required.",
        "sale_price": "This field is required.",
    }


def test_a_sale_input_error_is_a_sale_error(db):
    """So a caller catching SaleError, as the API does, still catches it."""
    with pytest.raises(psells.SaleError):
        psells.create_sale_from_text(db, 1, {"quantity": "x"})


def test_input_problems_are_found_before_the_product_is_looked_up(db):
    """No product 99, but the text is wrong: the text is reported."""
    with pytest.raises(psells.SaleInputError):
        psells.create_sale_from_text(db, 99, {"quantity": "0",
                                              "sale_price": "1"})


# Formatting money -------------------------------------------------------------
#
# format_cents had no test of its own until Phase 03b. It was covered only
# through the strings the menu functions print, which meant the one thing it
# got wrong, sign placement, was pinned in a dashboard test rather than named
# here. A page renders far more money than the CLI ever printed.

def test_format_cents_renders_dollars_and_cents():
    assert psells.format_cents(1234) == "$12.34"


def test_format_cents_pads_the_cents():
    """9 cents is $0.09, not $0.9."""
    assert psells.format_cents(9) == "$0.09"


def test_format_cents_renders_zero():
    assert psells.format_cents(0) == "$0.00"


def test_format_cents_puts_the_minus_outside_the_dollar_sign():
    """-$3.00, not $-3.00. Balance owing goes negative on an overpayment."""
    assert psells.format_cents(-300) == "-$3.00"


def test_format_cents_handles_a_negative_part_of_a_dollar():
    assert psells.format_cents(-9) == "-$0.09"


def test_format_cents_can_leave_out_the_dollar_sign():
    """For an edit form: text parse_money reads back as the same cents."""
    assert psells.format_cents(1234, symbol=False) == "12.34"
    assert psells.format_cents(-9, symbol=False) == "-0.09"
    assert psells.parse_money(psells.format_cents(1234, symbol=False)) == 1234


def test_format_cents_does_not_go_through_a_float():
    """A figure a float cannot hold exactly still renders exactly."""
    assert psells.format_cents(102030405060708090) == "$1020304050607080.90"


# The whole of recording a return with none of the asking.

def returns_stored(db):
    return [dict(row) for row in db.execute("SELECT * FROM returns ORDER BY id")]


def test_create_return_stores_the_row_and_returns_its_id(db):
    add_product(db, 1, quantity_received=10)

    return_id = psells.create_return(db, 1, 2, "2026-09-14", " damaged box ")

    assert returns_stored(db) == [{"id": return_id, "date": "2026-09-14",
                                   "item_id": 1, "quantity": 2,
                                   "notes": "damaged box"}]


def test_create_return_reduces_stock_and_leaves_the_intake(db):
    """Received 10, sold 3, returned 2: 5 remain, and 10 is still 10."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)

    psells.create_return(db, 1, 2, "2026-09-14", "")

    assert tuple(stock(db, 1)) == (3, 2, 5)
    assert db.execute("SELECT quantity_received FROM products").fetchone()[0] == 10


def test_create_return_moves_only_the_stock_figures(db):
    """Money is from sales and payments; a return changes neither."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)
    before = psells.dashboard_totals(db)

    psells.create_return(db, 1, 2, "2026-09-14", "")
    after = psells.dashboard_totals(db)

    assert after["total_returned"] == before["total_returned"] + 2
    assert after["total_available"] == before["total_available"] - 2
    for key in ("total_received", "total_sold", "total_revenue", "total_profit",
                "total_partner_share", "total_paid", "balance_owing"):
        assert after[key] == before[key], key


def test_create_return_stores_the_date_zero_padded(db):
    add_product(db, 1, quantity_received=10)

    psells.create_return(db, 1, 1, "2026-9-3", "")

    assert returns_stored(db)[0]["date"] == "2026-09-03"


@pytest.mark.parametrize("quantity, date_text, message", [
    (0, "2026-09-14", "Quantity must be at least 1."),
    (True, "2026-09-14", "Quantity must be at least 1."),
    (4, "2026-09-14", "Only 3 available, so 4 cannot be returned."),
    (1, "2026-02-30", "'2026-02-30' is not a date in YYYY-MM-DD form."),
])
def test_create_return_refuses_with_a_sentence(db, quantity, date_text,
                                               message):
    add_product(db, 1, quantity_received=3)

    with pytest.raises(psells.ReturnError) as refused:
        psells.create_return(db, 1, quantity, date_text, "")

    assert str(refused.value) == message
    assert returns_stored(db) == []


def test_create_return_refuses_a_product_with_no_stock(db):
    add_product(db, 1, quantity_received=2, name="Retired Diver")
    add_sale(db, 1, item_id=1, quantity=2)

    with pytest.raises(psells.ReturnError) as refused:
        psells.create_return(db, 1, 1, "2026-09-14", "")

    assert str(refused.value) == "Retired Diver has no stock available to return."


def test_create_return_for_a_product_that_does_not_exist(db):
    with pytest.raises(psells.ProductNotFound):
        psells.create_return(db, 99, 1, "2026-09-14", "")


# The whole of recording a payment with none of the asking.

def payments_stored(db):
    return [dict(row) for row in db.execute("SELECT * FROM payments ORDER BY id")]


def test_create_payment_stores_the_row_and_returns_its_id(db):
    payment_id = psells.create_payment(db, 15000, "2026-9-14", " e-transfer ")

    assert payments_stored(db) == [{"id": payment_id, "date": "2026-09-14",
                                    "amount_cents": 15000,
                                    "notes": "e-transfer"}]


def test_a_payment_moves_only_paid_and_the_balance(db):
    """Balance owing is partner share earned minus paid, and nothing else."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=2, sale_price_cents=9000,
             partner_share_cents=3500)
    before = psells.dashboard_totals(db)

    psells.create_payment(db, 5000, "2026-09-14", "")
    after = psells.dashboard_totals(db)

    assert after["total_paid"] == before["total_paid"] + 5000
    assert after["balance_owing"] == before["balance_owing"] - 5000
    for key in before:
        if key not in ("total_paid", "balance_owing"):
            assert after[key] == before[key], key


def test_a_payment_of_zero_is_accepted(db):
    """Deliberate, as on the command line."""
    psells.create_payment(db, 0, "2026-09-14", "")

    assert payments_stored(db)[0]["amount_cents"] == 0


@pytest.mark.parametrize("amount, date_text, message", [
    (-1, "2026-09-14", "Amount cannot be negative."),
    (12.5, "2026-09-14", "Amount cannot be negative."),
    (True, "2026-09-14", "Amount cannot be negative."),
    (100, "2026-13-01", "'2026-13-01' is not a date in YYYY-MM-DD form."),
])
def test_create_payment_refuses_with_a_sentence(db, amount, date_text,
                                                message):
    with pytest.raises(psells.PaymentError) as refused:
        psells.create_payment(db, amount, date_text, "")

    assert str(refused.value) == message
    assert payments_stored(db) == []


def test_create_payment_from_text_reports_every_problem_at_once(db):
    with pytest.raises(psells.PaymentInputError) as refused:
        psells.create_payment_from_text(db, {"amount": "abc",
                                             "date": "2026-02-30"})

    assert refused.value.problems == {
        "amount": psells.MONEY_TEXT_PROBLEM,
        "date": "Please enter a valid date in YYYY-MM-DD format.",
    }
    assert isinstance(refused.value, psells.PaymentError)


def test_all_payments_are_listed_oldest_first(db):
    psells.create_payment(db, 100, "2026-09-14", "b")
    psells.create_payment(db, 200, "2026-09-01", "a")

    assert [p["amount_cents"] for p in psells.all_payments(db)] == [100, 200]


# Deleting a product with none of the asking.

def products_left(db):
    return [row[0] for row in db.execute("SELECT id FROM products ORDER BY id")]


def test_a_product_with_no_history_has_no_blocker_and_is_deleted(db):
    add_product(db, 1, quantity_received=5)
    add_product(db, 2, quantity_received=5)

    assert psells.deletion_blocker(db, 1) is None

    psells.delete_product(db, 1)

    assert products_left(db) == [2]


@pytest.mark.parametrize("sales, returns, sentence", [
    (1, 0, "This product has 1 sale recorded against it."),
    (2, 0, "This product has 2 sales recorded against it."),
    (0, 1, "This product has 1 return recorded against it."),
    (2, 3, "This product has 2 sales and 3 returns recorded against it."),
])
def test_history_blocks_the_delete_with_a_sentence(db, sales, returns,
                                                   sentence):
    add_product(db, 1, quantity_received=10)
    for n in range(sales):
        add_sale(db, n + 1, item_id=1, quantity=1)
    for n in range(returns):
        add_return(db, n + 1, item_id=1, quantity=1)

    assert psells.deletion_blocker(db, 1) == sentence

    with pytest.raises(psells.DeleteRefused) as refused:
        psells.delete_product(db, 1)

    assert str(refused.value) == sentence
    assert products_left(db) == [1]


def test_deleting_a_product_that_does_not_exist(db):
    with pytest.raises(psells.ProductNotFound):
        psells.delete_product(db, 99)


def test_when_the_database_still_refuses_it_is_a_sentence(db):
    """Something points at the product that deletion_blocker does not know
    about: here, a table added for the test. The database refuses, and that
    arrives as DeleteRefused, not as an IntegrityError.

    The setup is committed first. A refused write inside `with connection:`
    rolls back everything uncommitted on the connection, and the helpers do
    not commit, so without this the refusal would also remove the product the
    test just inserted. The application commits every write it makes, so this
    matches the state it is really in.
    """
    add_product(db, 1, quantity_received=5)
    db.execute("CREATE TABLE notes_elsewhere (item_id INTEGER NOT NULL "
               "REFERENCES products(id) ON DELETE RESTRICT)")
    db.execute("INSERT INTO notes_elsewhere VALUES (1)")
    db.commit()

    assert psells.deletion_blocker(db, 1) is None

    with pytest.raises(psells.DeleteRefused) as refused:
        psells.delete_product(db, 1)

    assert "The database refused the deletion." in str(refused.value)
    assert products_left(db) == [1]


# Where the data lives --------------------------------------------------------

def test_the_default_paths_sit_beside_psells_not_beside_the_shell(monkeypatch):
    """An absolute path under the project, whatever directory anybody is in."""
    monkeypatch.delenv("PSELLS_DB", raising=False)

    path = psells.path_from_environment("PSELLS_DB", "data", "psells.db")

    assert os.path.isabs(path)
    assert path == os.path.join(psells.PROJECT_DIR, "data", "psells.db")


def test_the_environment_overrides_the_default(monkeypatch):
    monkeypatch.setenv("PSELLS_DB", "/tmp/somewhere-else.db")

    assert psells.path_from_environment(
        "PSELLS_DB", "data", "psells.db"
    ) == "/tmp/somewhere-else.db"


def test_an_empty_variable_counts_as_unset(monkeypatch):
    """PSELLS_DB= means use the default, not open the file named "".

    Exporting a variable as empty is a normal way to say "never mind", and
    os.environ.get would otherwise hand back the empty string as a real answer.
    """
    monkeypatch.setenv("PSELLS_DB", "")

    assert psells.path_from_environment(
        "PSELLS_DB", "data", "psells.db"
    ) == os.path.join(psells.PROJECT_DIR, "data", "psells.db")
