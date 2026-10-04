"""The stock lists and the history lists in psells.py.

Which products are in stock and which ran out, why one ran out, and every sale,
return and payment, newest first. The inventory, out-of-stock and history
pages, the API and the command line all call these functions, so the rules
are tested here once; the other layers are tested against them. Every value
is invented.
"""

import datetime

import pytest

import psells
from helpers import add_payment, add_product, add_return, add_sale


def ids(rows):
    return [row["id"] for row in rows]


def a_shop(db):
    """Five products, one in each state that matters:
    1 untouched, 2 partly sold, 3 sold out, 4 all returned, 5 a mix to zero."""
    for product_id in range(1, 6):
        add_product(db, product_id, quantity_received=3)
    add_sale(db, 1, item_id=2, quantity=1)
    add_sale(db, 2, item_id=3, quantity=3)
    add_return(db, 1, item_id=4, quantity=3)
    add_sale(db, 3, item_id=5, quantity=2)
    add_return(db, 2, item_id=5, quantity=1)


# The two stock lists -----------------------------------------------------------

def test_every_product_is_in_exactly_one_of_the_two_lists(db):
    a_shop(db)

    in_stock = ids(psells.in_stock_products(db))
    out_of_stock = ids(psells.out_of_stock_products(db))

    assert in_stock == [1, 2]
    assert out_of_stock == [3, 4, 5]
    assert sorted(in_stock + out_of_stock) == ids(psells.all_products(db))
    assert not set(in_stock) & set(out_of_stock)


def test_a_sale_of_the_last_unit_moves_a_product_between_the_lists(db):
    add_product(db, 1, quantity_received=1)
    assert ids(psells.in_stock_products(db)) == [1]

    psells.create_sale(db, 1, 1, 9000, "2026-09-02")

    assert psells.in_stock_products(db) == []
    assert ids(psells.out_of_stock_products(db)) == [1]


def test_a_search_on_the_inventory_never_finds_an_out_of_stock_product(db):
    add_product(db, 1, quantity_received=2, name="Round glasses")
    add_product(db, 2, quantity_received=1, name="Square glasses")
    add_product(db, 3, quantity_received=2, name="Leather belt")
    add_sale(db, 1, item_id=2, quantity=1)

    found = psells.find_items_by_name_or_category(
        psells.in_stock_products(db), "glasses")

    assert ids(found) == [1]


def test_with_no_products_both_lists_are_empty(db):
    assert psells.in_stock_products(db) == []
    assert psells.out_of_stock_products(db) == []


# Why a product ran out ---------------------------------------------------------

def test_all_three_reasons(db):
    a_shop(db)
    reasons = {row["id"]: psells.out_of_stock_reason(row)
               for row in psells.out_of_stock_products(db)}

    assert reasons == {
        3: "Sold out",
        4: "Returned",
        5: "2 sold, 1 returned of 3",
    }


def test_a_product_with_units_left_has_no_reason(db):
    a_shop(db)
    in_stock = psells.in_stock_products(db)[0]

    with pytest.raises(ValueError):
        psells.out_of_stock_reason(in_stock)


# Sales history -----------------------------------------------------------------

def test_sales_come_newest_first_and_the_newest_id_first_on_one_date(db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=1, date="2026-08-03")
    add_sale(db, 2, item_id=1, quantity=1, date="2026-09-14")
    add_sale(db, 3, item_id=1, quantity=1, date="2026-08-20")
    add_sale(db, 4, item_id=1, quantity=1, date="2026-09-14")

    assert ids(psells.sales_history(db)) == [4, 2, 3, 1]


def test_a_sale_row_carries_its_product_and_its_own_figures(db):
    add_product(db, 7, quantity_received=5, name="Trail runner",
                category="Shoes")
    add_sale(db, 1, item_id=7, quantity=2, sale_price_cents=12500,
             partner_share_cents=4000, date="2026-09-10")

    sale = psells.sales_history(db)[0]

    assert (sale["date"], sale["item_id"], sale["name"], sale["category"]) == (
        datetime.date(2026, 9, 10), 7, "Trail runner", "Shoes")
    assert sale["quantity"] == 2
    assert sale["sale_price_cents"] == 12500
    assert sale["sale_total_cents"] == 25000
    assert sale["partner_cut_cents"] == 8000
    assert sale["profit_cents"] == 17000


def test_editing_a_product_never_changes_a_past_sale(db, partner_rate):
    add_product(db, 1, quantity_received=5, name="Trail runner")
    psells.create_sale(db, 1, 2, 9000, "2026-09-01")
    before = dict(psells.sales_history(db)[0])

    # New prices, a new share, a new name: the product is not the sale.
    psells.update_product(
        db, 1, category="Shoes", name="Trail runner II", quantity_received=5,
        retail_discontinued=False, retail_price_cents=20000,
        listed_price_cents=18000, condition="Brand New", notes="",
        partner_share_mode="custom_amount", partner_share_percent=None,
        partner_share_amount_cents=7777)
    after = dict(psells.sales_history(db)[0])

    for figure in ("quantity", "sale_price_cents", "partner_share_cents",
                   "sale_total_cents", "partner_cut_cents", "profit_cents"):
        assert after[figure] == before[figure], figure
    # Only the name shown beside it follows the product.
    assert after["name"] == "Trail runner II"


def test_the_sales_history_adds_up_to_the_dashboard(db):
    a_shop(db)
    add_product(db, 6, quantity_received=4)
    add_sale(db, 4, item_id=6, quantity=2, sale_price_cents=11000,
             partner_share_cents=3300)

    sales = psells.sales_history(db)
    totals = psells.dashboard_totals(db)

    assert sum(s["quantity"] for s in sales) == totals["total_sold"]
    assert sum(s["sale_total_cents"] for s in sales) == totals["total_revenue"]
    assert sum(s["partner_cut_cents"] for s in sales) \
        == totals["total_partner_share"]
    assert sum(s["profit_cents"] for s in sales) == totals["total_profit"]


def test_no_sales_is_an_empty_history(db):
    assert psells.sales_history(db) == []


# Returns and payments ----------------------------------------------------------

def test_returns_come_newest_first_with_their_product_and_notes(db):
    add_product(db, 1, quantity_received=10, name="Canvas cap", category="Hats")
    add_return(db, 1, item_id=1, quantity=1, date="2026-08-01", notes="faded")
    add_return(db, 2, item_id=1, quantity=2, date="2026-09-05", notes="")
    add_return(db, 3, item_id=1, quantity=1, date="2026-09-05", notes="torn")

    returns = psells.returns_history(db)

    assert ids(returns) == [3, 2, 1]
    assert (returns[0]["name"], returns[0]["category"], returns[0]["quantity"],
            returns[0]["notes"]) == ("Canvas cap", "Hats", 1, "torn")


def test_payments_come_newest_first_and_add_up_to_total_paid(db):
    add_payment(db, 1, 5000, date="2026-07-15", note="first")
    add_payment(db, 2, 2500, date="2026-09-01")
    add_payment(db, 3, 1250, date="2026-09-01", note="top-up")

    payments = psells.payments_history(db)

    assert ids(payments) == [3, 2, 1]
    assert sum(p["amount_cents"] for p in payments) \
        == psells.dashboard_totals(db)["total_paid"]


def test_no_returns_or_payments_are_empty_histories(db):
    assert psells.returns_history(db) == []
    assert psells.payments_history(db) == []
