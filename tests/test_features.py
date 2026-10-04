"""End-to-end tests of the functions that prompt and print.

These call the feature functions the way the menu does, with input faked and
output captured, and check what the user would actually see. test_domain.py
covers the calculations underneath; a failure here means the application is
wrong rather than the arithmetic.

They assert on particular facts rather than on whole blocks of output, so
rewording a heading does not fail a test that nothing broke.
"""

from datetime import date

import pytest

import psells

from helpers import (add_payment, add_product, add_return, add_sale,
                     add_shop)


def test_dashboard_on_an_empty_database(db, capsys):
    """Every money figure reads $0.00 rather than $0, $0.0 or a bare 0."""
    psells.view_dashboard(db)

    printed = capsys.readouterr().out

    assert "Total received: 0" in printed
    assert "Total revenue: $0.00" in printed
    assert "Total profit: $0.00" in printed
    assert "Total partner share earned: $0.00" in printed
    assert "Total paid: $0.00" in printed
    assert "Balance owing: $0.00" in printed


def seed_dashboard(connection):
    """Two products, two sales, one return, one payment.

    Every figure below is worked out by hand, so the tests check the arithmetic
    rather than agree with whatever the code produces. No two figures are equal,
    so a line printed under the wrong label cannot pass by coincidence.

        received   10 + 5                  = 15
        sold       2 + 1                   = 3
        returned   1                       = 1
        available  15 - 3 - 1              = 11
        revenue    2*19999 + 1*5           = 40003   $400.03
        partner    2*8000  + 1*2           = 16002   $160.02
        profit     40003 - 16002           = 24001   $240.01
        paid       10000                   = 10000   $100.00
        owing      16002 - 10000           = 6002    $60.02

    The 5 cent sale is deliberate. It drags the totals onto cents values that
    need a leading zero, which is where money formatting goes wrong quietly.
    """
    add_product(connection, 1, quantity_received=10)
    add_product(connection, 2, quantity_received=5)

    add_sale(connection, 1, item_id=1, quantity=2,
             sale_price_cents=19999, partner_share_cents=8000)
    add_sale(connection, 2, item_id=2, quantity=1,
             sale_price_cents=5, partner_share_cents=2)

    add_return(connection, 1, item_id=1, quantity=1)

    add_payment(connection, 1, amount_cents=10000)


def test_dashboard_prints_the_quantities(db, capsys):
    seed_dashboard(db)

    psells.view_dashboard(db)

    printed = capsys.readouterr().out

    assert "Total received: 15" in printed
    assert "Total sold: 3" in printed
    assert "Total available: 11" in printed
    assert "Total returned: 1" in printed


def test_dashboard_prints_the_money(db, capsys):
    seed_dashboard(db)

    psells.view_dashboard(db)

    printed = capsys.readouterr().out

    assert "Total revenue: $400.03" in printed
    assert "Total profit: $240.01" in printed
    assert "Total partner share earned: $160.02" in printed
    assert "Total paid: $100.00" in printed
    assert "Balance owing: $60.02" in printed


def test_dashboard_shows_an_overpayment_as_a_negative_balance(db, capsys):
    """Paying the partner more than is owed leaves a negative balance.

    The minus goes outside the dollar sign. This used to read $-3.00, which was
    pinned here rather than fixed while Phase 03 was recording behaviour; the
    fix is Phase 03b's, taken before a browser started showing it.
    """
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1,
             sale_price_cents=2000, partner_share_cents=500)
    add_payment(db, 1, amount_cents=800)

    psells.view_dashboard(db)

    assert "Balance owing: -$3.00" in capsys.readouterr().out


def test_inventory_says_so_when_it_is_empty(db, capsys):
    psells.view_inventory(db)

    assert "No products in stock." in capsys.readouterr().out


def test_inventory_prints_every_field_of_a_product(db, capsys, partner_rate):
    """The listing is the screen Phase 03b replaces, so every line is pinned.

    Partner Cut is 40 percent of the 100.00 retail price, from the rate the
    partner_rate fixture pins rather than from the real configuration.
    """
    add_product(db, 1, quantity_received=4, name="Jordan 1 Chicago")

    psells.view_inventory(db)

    printed = capsys.readouterr().out

    assert "ID: 1" in printed
    assert "Name: Jordan 1 Chicago" in printed
    assert "Category: Shoes" in printed
    assert "Available: 4" in printed
    assert "Listed Price: $90.00" in printed
    assert "Partner Cut: $40.00" in printed
    assert "Discontinued: No" in printed
    assert "Condition: Brand New" in printed


def test_inventory_lists_every_product_in_id_order(db, capsys, partner_rate):
    """all_products orders by id deliberately, so the order is worth holding.

    Without ORDER BY, the database makes no promise at all. It would happen to come
    back in id order today and change the day a query plan changes.
    """
    add_product(db, 1, quantity_received=1, name="First")
    add_product(db, 2, quantity_received=1, name="Second")
    add_product(db, 3, quantity_received=1, name="Third")

    psells.view_inventory(db)

    printed = capsys.readouterr().out

    assert printed.index("Name: First") < printed.index("Name: Second")
    assert printed.index("Name: Second") < printed.index("Name: Third")


def test_inventory_shows_stock_after_sales_and_returns(db, capsys, partner_rate):
    """Received 10, sold 3, returned 1, so 6 are on the shelf."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)
    add_return(db, 1, item_id=1, quantity=1)

    psells.view_inventory(db)

    assert "Available: 6" in capsys.readouterr().out


def test_inventory_shows_a_retail_discontinued_product(db, capsys):
    """No partner_rate fixture here, deliberately.

    A fixed-amount product never consults the configuration, so this test also
    proves that path does not read the file.
    """
    add_product(
        db, 1, quantity_received=2,
        name="Discontinued Watch",
        retail_discontinued=1,
        retail_price_cents=0,
        partner_share_mode="custom_amount",
        partner_share_amount_cents=2500,
    )

    psells.view_inventory(db)

    printed = capsys.readouterr().out

    assert "Discontinued: Yes" in printed
    assert "Partner Cut: $25.00" in printed


# Categories ------------------------------------------------------------------

def test_categories_says_so_when_inventory_is_empty(db, capsys):
    psells.list_categories(db)

    assert "Inventory is empty." in capsys.readouterr().out


def test_categories_lists_each_one_once_with_a_count(db, capsys):
    add_product(db, 1, quantity_received=1, category="Bags")
    add_product(db, 2, quantity_received=1, category="Sunglasses")
    add_product(db, 3, quantity_received=1, category="Sunglasses")

    psells.list_categories(db)

    printed = capsys.readouterr().out

    assert printed.count("Bags") == 1
    assert printed.count("Sunglasses") == 1
    assert "2 categories, 3 products" in printed


def test_categories_are_alphabetical(db, capsys):
    for product_id, category in enumerate(["Watches", "Bags", "Shoes"], start=1):
        add_product(db, product_id, quantity_received=1, category=category)

    psells.list_categories(db)

    printed = capsys.readouterr().out

    assert printed.index("Bags") < printed.index("Shoes")
    assert printed.index("Shoes") < printed.index("Watches")


def test_categories_are_padded_to_the_longest_name(db, capsys):
    """The one place the shape of the output is the feature rather than dressing.

    The counts are meant to line up in a column, which needs the width of the
    longest name. A width bug is invisible until a long category name arrives,
    so the aligned lines are asserted exactly.
    """
    add_product(db, 1, quantity_received=1, category="Bags")
    add_product(db, 2, quantity_received=1, category="Sunglasses")
    add_product(db, 3, quantity_received=1, category="Sunglasses")

    psells.list_categories(db)

    lines = capsys.readouterr().out.splitlines()

    assert "Bags        1" in lines
    assert "Sunglasses  2" in lines


# Search ----------------------------------------------------------------------

def test_search_prints_a_product_matching_the_name(db, capsys, answers,
                                                   partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")
    add_product(db, 2, quantity_received=3, name="Leather Tote")

    answers("jordan")
    psells.search(db)

    printed = capsys.readouterr().out

    assert "Name: Jordan 1 Chicago" in printed
    assert "Leather Tote" not in printed


def test_search_prints_a_product_matching_the_category(db, capsys, answers,
                                                       partner_rate):
    """The half of search added in Phase 02: the term need not be in the name."""
    add_product(db, 1, quantity_received=3, name="Leather Tote", category="Bags")

    answers("bags")
    psells.search(db)

    assert "Name: Leather Tote" in capsys.readouterr().out


def test_search_says_so_when_nothing_matches(db, capsys, answers, partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("kettle")
    psells.search(db)

    assert "No products in stock found." in capsys.readouterr().out


def test_search_asks_again_after_a_blank_term(db, capsys, answers, partner_rate):
    """ask_text rejects a blank answer and asks again, consuming two replies.

    Nothing tested these loops before, and they are the most likely place for a
    change to go unnoticed, because a broken one still looks like a prompt.
    """
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("   ", "jordan")
    psells.search(db)

    printed = capsys.readouterr().out

    assert "Input cannot be blank. Please try again." in printed
    assert "Name: Jordan 1 Chicago" in printed


# Record a payment ------------------------------------------------------------
#
# The first feature that writes. These check the row that lands in the database
# as well as what the user was told, because a function that prints "Payment
# recorded." and stores nothing passes any test that only reads the screen.

def only_payment(connection):
    return connection.execute("SELECT * FROM payments").fetchone()


def test_a_payment_is_stored_and_confirmed(db, capsys, answers):
    answers("2026-09-14", "150.00", "e-transfer")
    psells.record_payment(db)

    payment = only_payment(db)

    assert payment["date"] == date(2026, 9, 14)
    assert payment["amount_cents"] == 15000
    assert payment["notes"] == "e-transfer"
    assert "Payment recorded." in capsys.readouterr().out


def test_a_blank_date_means_today(db, capsys, answers):
    answers("", "50", "")
    psells.record_payment(db)

    assert only_payment(db)["date"] == date.today()


def test_an_amount_that_is_not_a_number_is_refused(db, capsys, answers):
    answers("2026-09-14", "abc", "12.50", "")
    psells.record_payment(db)

    assert only_payment(db)["amount_cents"] == 1250
    assert "Please enter an amount in dollars" in capsys.readouterr().out


def test_a_third_decimal_place_is_refused(db, capsys, answers):
    """A tenth of a cent is not an amount of money.

    parse_money refuses it rather than rounding, because rounding would store a
    different figure from the one that was typed and say nothing about it.
    """
    answers("2026-09-14", "12.505", "12.50", "")
    psells.record_payment(db)

    assert only_payment(db)["amount_cents"] == 1250


def test_a_negative_amount_is_refused(db, capsys, answers):
    answers("2026-09-14", "-5.00", "5.00", "")
    psells.record_payment(db)

    assert only_payment(db)["amount_cents"] == 500
    assert "Value must be at least $0.00." in capsys.readouterr().out


def test_a_payment_of_zero_is_accepted(db, capsys, answers):
    """Deliberate, and confirmed as wanted rather than tolerated.

    Recorded here so that if it ever changes, it changes on purpose.
    """
    answers("2026-09-14", "0", "")
    psells.record_payment(db)

    assert only_payment(db)["amount_cents"] == 0


def test_a_date_that_does_not_exist_is_refused(db, capsys, answers):
    """There is no 13th month. The prompt asks again rather than storing it.

    The schema would also refuse this, but the point is that the user is asked
    again rather than meeting a constraint error.
    """
    answers("2026-13-01", "2026-09-14", "10", "")
    psells.record_payment(db)

    assert only_payment(db)["date"] == date(2026, 9, 14)
    assert "Please enter a valid date in YYYY-MM-DD format." in capsys.readouterr().out


# Record a sale ---------------------------------------------------------------
#
# The most important function in the application. It is the only place a
# partner share is frozen onto a row, and the only place stock comes down.

def only_sale(connection):
    return connection.execute("SELECT * FROM sales").fetchone()


def available(connection, product_id):
    return connection.execute(
        "SELECT quantity_available FROM products_view WHERE id = %s",
        (product_id,)
    ).fetchone()["quantity_available"]


def test_a_sale_is_stored_and_reduces_stock(db, capsys, answers, partner_rate):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("jordan", "2", "89.99", "2026-09-14")
    psells.record_sale(db)

    sale = only_sale(db)

    assert sale["item_id"] == 1
    assert sale["quantity"] == 2
    assert sale["sale_price_cents"] == 8999
    assert sale["date"] == date(2026, 9, 14)
    assert available(db, 1) == 8
    assert "Sale recorded." in capsys.readouterr().out


def test_the_partner_cut_is_frozen_onto_the_sale(db, answers, partner_rate,
                                                 monkeypatch):
    """The rule the whole data model exists to protect.

    The partner's cut is worked out once, at the moment of sale, and stored on
    the row. Changing the default rate afterwards must not reach back and alter
    what was already agreed on a sale that has happened.

    The second half of this test proves the rate really did change, so a stored
    figure that stayed put cannot be explained by the change not taking effect.
    """
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("jordan", "1", "89.99", "2026-09-14")
    psells.record_sale(db)

    assert only_sale(db)["partner_share_cents"] == 4000

    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 10.0)

    product = psells.all_products(db)[0]

    assert psells.partner_share_for(product) == 1000
    assert only_sale(db)["partner_share_cents"] == 4000


def test_selling_more_than_is_available_is_refused(db, capsys, answers,
                                                   partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("jordan", "5", "3", "10.00", "")
    psells.record_sale(db)

    assert only_sale(db)["quantity"] == 3
    assert available(db, 1) == 0
    assert "Value must be at most 3." in capsys.readouterr().out


def test_selling_none_is_refused(db, capsys, answers, partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("jordan", "0", "1", "10.00", "")
    psells.record_sale(db)

    assert only_sale(db)["quantity"] == 1
    assert "Value must be at least 1." in capsys.readouterr().out


def test_a_sold_out_product_cannot_be_sold_again(db, capsys, answers,
                                                 partner_rate):
    add_product(db, 1, quantity_received=2, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=2)

    answers("jordan")
    psells.record_sale(db)

    assert "No stock available to sell." in capsys.readouterr().out
    assert db.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"] == 1


def test_selling_from_an_empty_inventory(db, capsys, answers, partner_rate):
    """No question is asked at all, which the empty answer queue proves.

    If this ever started prompting first, the queue would run dry and the test
    would fail with StopIteration rather than quietly passing.
    """
    answers()
    psells.record_sale(db)

    assert "Inventory is empty." in capsys.readouterr().out


def test_selling_a_product_that_does_not_match(db, capsys, answers,
                                               partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("kettle")
    psells.record_sale(db)

    assert "No products found." in capsys.readouterr().out
    assert db.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"] == 0


def test_choosing_between_two_matches_by_id(db, capsys, answers, partner_rate):
    """A term matching two products lists both and asks which.

    99 is not one of them, so it is refused and the question is asked again.
    """
    add_product(db, 1, quantity_received=3, name="Nike Air Max 90")
    add_product(db, 2, quantity_received=3, name="Nike Air Force 1")

    answers("nike", "99", "2", "1", "50.00", "")
    psells.record_sale(db)

    printed = capsys.readouterr().out

    assert "Multiple products found:" in printed
    assert "Invalid ID. Please choose one of the IDs shown above." in printed
    assert only_sale(db)["item_id"] == 2


# Record a return -------------------------------------------------------------

def only_return(connection):
    return connection.execute("SELECT * FROM returns").fetchone()


def received(connection, product_id):
    return connection.execute(
        "SELECT quantity_received FROM products WHERE id = %s",
        (product_id,)
    ).fetchone()["quantity_received"]


def test_a_return_is_stored_and_reduces_stock(db, capsys, answers,
                                              partner_rate):
    """Received 10, sold 3, returned 2, so 5 remain."""
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=3)

    answers("jordan", "2", "2026-09-14", "damaged box")
    psells.record_return(db)

    returned = only_return(db)

    assert returned["item_id"] == 1
    assert returned["quantity"] == 2
    assert returned["date"] == date(2026, 9, 14)
    assert returned["notes"] == "damaged box"
    assert available(db, 1) == 5
    assert "Return recorded." in capsys.readouterr().out


def test_a_return_does_not_change_the_intake_quantity(db, answers,
                                                      partner_rate):
    """The Phase 02 reversal, pinned.

    quantity_received means the units originally taken in and nothing else. It
    used to be decremented, which made it mean units still held and left no
    record of the original figure anywhere. A return is now its own row and the
    intake number is never touched.
    """
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("jordan", "4", "", "")
    psells.record_return(db)

    assert received(db, 1) == 10
    assert available(db, 1) == 6


def test_returning_more_than_is_available_is_refused(db, capsys, answers,
                                                     partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("jordan", "5", "3", "", "")
    psells.record_return(db)

    assert only_return(db)["quantity"] == 3
    assert available(db, 1) == 0
    assert "Value must be at most 3." in capsys.readouterr().out


def test_returning_none_is_refused(db, capsys, answers, partner_rate):
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")

    answers("jordan", "0", "1", "", "")
    psells.record_return(db)

    assert only_return(db)["quantity"] == 1
    assert "Value must be at least 1." in capsys.readouterr().out


def test_a_product_with_no_stock_left_cannot_be_returned(db, capsys, answers,
                                                         partner_rate):
    add_product(db, 1, quantity_received=2, name="Jordan 1 Chicago")
    add_return(db, 1, item_id=1, quantity=2)

    answers("jordan")
    psells.record_return(db)

    assert "No stock available to return." in capsys.readouterr().out
    assert db.execute("SELECT COUNT(*) AS n FROM returns").fetchone()["n"] == 1


def test_returning_from_an_empty_inventory(db, capsys, answers, partner_rate):
    answers()
    psells.record_return(db)

    assert "Inventory is empty." in capsys.readouterr().out


# Delete a product ------------------------------------------------------------

def product_count(connection):
    return connection.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]


def test_a_product_with_no_history_is_deleted(db, capsys, answers,
                                              partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    answers("jordan", "yes")
    psells.delete(db)

    assert product_count(db) == 0
    assert "Product deleted." in capsys.readouterr().out


def test_answering_no_cancels_the_deletion(db, capsys, answers, partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    answers("jordan", "no")
    psells.delete(db)

    assert product_count(db) == 1
    assert "Cancelled." in capsys.readouterr().out


def test_a_product_with_a_sale_is_refused_without_being_asked(db, capsys,
                                                              answers,
                                                              partner_rate):
    """Issue I1, closed in Phase 02, checked here for the first time.

    Two things matter. The product survives, and the refusal comes before the
    confirmation question rather than after it. Queueing only the search term
    is what proves the second: if this ever asked to confirm before checking
    what points at the product, the queue would run dry and this would fail.
    """
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=1)

    answers("jordan")
    psells.delete(db)

    printed = capsys.readouterr().out

    assert product_count(db) == 1
    assert "This product has 1 sale recorded against it." in printed
    assert "Deleting it would lose that history, so it is refused." in printed


def test_the_refusal_counts_more_than_one_sale(db, capsys, answers,
                                               partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=1)
    add_sale(db, 2, item_id=1, quantity=1)

    answers("jordan")
    psells.delete(db)

    assert "This product has 2 sales recorded against it." in capsys.readouterr().out


def test_the_refusal_names_sales_and_returns_together(db, capsys, answers,
                                                      partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=1)
    add_return(db, 1, item_id=1, quantity=1)

    answers("jordan")
    psells.delete(db)

    printed = capsys.readouterr().out

    assert "This product has 1 sale and 1 return recorded against it." in printed


def test_an_unrecognised_confirmation_is_refused(db, capsys, answers,
                                                 partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    answers("jordan", "maybe", "yes")
    psells.delete(db)

    assert product_count(db) == 0
    assert "Invalid choice. Please try again." in capsys.readouterr().out


def test_deleting_from_an_empty_inventory(db, capsys, answers, partner_rate):
    answers()
    psells.delete(db)

    assert "Inventory is empty." in capsys.readouterr().out


def test_deleting_a_product_that_does_not_match(db, capsys, answers,
                                                partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    answers("kettle")
    psells.delete(db)

    assert product_count(db) == 1
    assert "No products found." in capsys.readouterr().out


# Add a product ---------------------------------------------------------------
#
# The longest prompt sequence in the application. In order: category, name,
# quantity, discontinued, retail price, listed price, condition, notes, then the
# partner-share block, which is itself one or two more questions depending on
# the mode. The length of each answer queue below is a claim about that order.

def only_product(connection):
    return connection.execute("SELECT * FROM products").fetchone()


def test_a_product_is_added_on_the_default_share(db, capsys, answers):
    answers("Shoes", "Jordan 1 Chicago", "10", "no",
            "100.00", "90.00", "Brand New", "boxed", "default")
    psells.add(db)

    product = only_product(db)

    assert product["category"] == "Shoes"
    assert product["name"] == "Jordan 1 Chicago"
    assert product["quantity_received"] == 10
    assert product["retail_discontinued"] == 0
    assert product["retail_price_cents"] == 10000
    assert product["listed_price_cents"] == 9000
    assert product["condition"] == "Brand New"
    assert product["notes"] == "boxed"
    assert product["partner_share_mode"] == "default"
    assert product["partner_share_percent"] is None
    assert product["partner_share_amount_cents"] is None
    assert "Product added successfully." in capsys.readouterr().out


def test_a_product_is_added_on_a_custom_percentage(db, answers):
    answers("Shoes", "Jordan 1 Chicago", "10", "no",
            "100.00", "90.00", "Brand New", "", "custom_percent", "35.5")
    psells.add(db)

    product = only_product(db)

    assert product["partner_share_mode"] == "custom_percent"
    assert product["partner_share_percent"] == 35.5
    assert product["partner_share_amount_cents"] is None


def test_a_product_is_added_on_a_fixed_amount(db, answers):
    answers("Shoes", "Jordan 1 Chicago", "10", "no",
            "100.00", "90.00", "Brand New", "", "custom_amount", "25.00")
    psells.add(db)

    product = only_product(db)

    assert product["partner_share_mode"] == "custom_amount"
    assert product["partner_share_percent"] is None
    assert product["partner_share_amount_cents"] == 2500


def test_a_discontinued_product_is_never_asked_for_a_mode(db, answers):
    """Two questions are skipped, and the queue length is what proves it.

    A product discontinued at retail has no retail price to take a percentage
    of, so it is not asked for one, and the fixed amount is the only mode
    available rather than being offered and then refused. There are eight
    answers here where the ordinary path takes nine, and a mode question
    appearing would eat the partner amount, fail the choice, and run the queue
    dry.
    """
    answers("Watches", "Retired Diver", "2", "yes",
            "40.00", "Used", "", "12.50")
    psells.add(db)

    product = only_product(db)

    assert product["retail_discontinued"] == 1
    assert product["retail_price_cents"] == 0
    assert product["listed_price_cents"] == 4000
    assert product["partner_share_mode"] == "custom_amount"
    assert product["partner_share_amount_cents"] == 1250


def test_a_retail_price_of_zero_is_refused(db, capsys, answers):
    """Zero is reserved for products discontinued at retail.

    The schema refuses the combination outright, so the prompt has to catch it
    first. Otherwise a fully typed product ends in a constraint error.
    """
    answers("Shoes", "Jordan 1 Chicago", "10", "no",
            "0", "100.00", "90.00", "Brand New", "", "default")
    psells.add(db)

    assert only_product(db)["retail_price_cents"] == 10000
    assert "Value must be at least $0.01." in capsys.readouterr().out


def test_a_blank_category_is_refused(db, capsys, answers):
    answers("", "Shoes", "Jordan 1 Chicago", "10", "no",
            "100.00", "90.00", "Brand New", "", "default")
    psells.add(db)

    assert only_product(db)["category"] == "Shoes"
    assert "Input cannot be blank. Please try again." in capsys.readouterr().out


def test_a_quantity_of_zero_is_refused(db, capsys, answers):
    answers("Shoes", "Jordan 1 Chicago", "0", "10", "no",
            "100.00", "90.00", "Brand New", "", "default")
    psells.add(db)

    assert only_product(db)["quantity_received"] == 10
    assert "Value must be at least 1." in capsys.readouterr().out


def test_an_unrecognised_discontinued_answer_is_refused(db, capsys, answers):
    answers("Shoes", "Jordan 1 Chicago", "10", "maybe", "no",
            "100.00", "90.00", "Brand New", "", "default")
    psells.add(db)

    assert only_product(db)["retail_discontinued"] == 0
    assert "Invalid choice. Please try again." in capsys.readouterr().out


def test_a_partner_percentage_above_one_hundred_is_refused(db, capsys, answers):
    answers("Shoes", "Jordan 1 Chicago", "10", "no",
            "100.00", "90.00", "Brand New", "", "custom_percent", "150", "35")
    psells.add(db)

    assert only_product(db)["partner_share_percent"] == 35
    assert "Value must be at most 100." in capsys.readouterr().out


def test_a_partner_percentage_of_nan_is_refused(db, capsys, answers):
    """float() reads "nan" as a number, and nan passes the 0 to 100 check
    because it compares false with everything. Stored, it became NULL and add
    died on the schema's matrix constraint."""
    answers("Shoes", "Jordan 1 Chicago", "10", "no",
            "100.00", "90.00", "Brand New", "", "custom_percent", "nan", "35")
    psells.add(db)

    assert only_product(db)["partner_share_percent"] == 35
    assert "Please enter a valid number." in capsys.readouterr().out


def test_ask_float_refuses_every_non_finite_number(capsys, answers):
    """The one float prompt, used by add and by edit through
    ask_partner_share. Five refusals, then a number."""
    answers("nan", "NaN", "inf", "-inf", "infinity", "12.5")

    assert psells.ask_float("Percent: ", min_value=0, max_value=100) == 12.5
    assert capsys.readouterr().out.count("Please enter a valid number.") == 5


# Edit a product, part one: the keep-current convention ------------------------
#
# Every field in edit offers the current value in brackets and takes Enter to
# keep it. In order: category, name, quantity, discontinued, retail price,
# listed price, condition, notes, then the partner-share block.

def product_row(connection, product_id=1):
    row = connection.execute(
        "SELECT * FROM products WHERE id = %s", (product_id,)
    ).fetchone()

    return dict(row)


def test_pressing_enter_through_every_field_changes_nothing(db, answers,
                                                            partner_rate):
    """The convention the whole function rests on, checked in one go.

    Eight blank answers, one per field. The tenth answer is not blank because
    the partner-share question will not take one, which the next test covers.
    """
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago",
                category="Shoes", notes="boxed")

    before = product_row(db)

    answers("jordan", "", "", "", "", "", "", "", "", "no")
    psells.edit(db)

    assert product_row(db) == before


def test_the_partner_share_question_will_not_take_a_blank_answer(db, capsys,
                                                                 answers,
                                                                 partner_rate):
    """A known wrinkle, recorded rather than fixed.

    Every other prompt in edit takes Enter to keep the current value. This one
    uses ask_choice rather than ask_edit_choice, so a blank is refused and the
    question is asked again. Cosmetic, listed in the README, and pinned here so
    that whoever fixes it sees this test go red and knows to update it.
    """
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("jordan", "", "", "", "", "", "", "", "", "", "no")
    psells.edit(db)

    assert "Invalid choice. Please try again." in capsys.readouterr().out


def test_editing_the_category_and_the_name(db, capsys, answers, partner_rate):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago",
                category="Shoes")

    answers("jordan", "Sneakers", "Jordan 1 Bred", "", "", "", "", "", "", "no")
    psells.edit(db)

    product = product_row(db)

    assert product["category"] == "Sneakers"
    assert product["name"] == "Jordan 1 Bred"
    assert "Product updated successfully." in capsys.readouterr().out


def test_editing_the_prices(db, answers, partner_rate):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("jordan", "", "", "", "", "250.00", "199.99", "", "", "no")
    psells.edit(db)

    product = product_row(db)

    assert product["retail_price_cents"] == 25000
    assert product["listed_price_cents"] == 19999


def test_notes_cannot_be_cleared(db, answers, partner_rate):
    """Issue I8, pinned as it stands rather than fixed.

    A blank answer means keep the current value everywhere in edit, which
    leaves no way to blank a note that already has text. Recorded so the
    behaviour is a decision rather than a surprise.
    """
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago",
                notes="boxed")

    answers("jordan", "", "", "", "", "", "", "", "", "no")
    psells.edit(db)

    assert product_row(db)["notes"] == "boxed"


def test_the_intake_cannot_drop_below_what_has_already_gone(db, capsys,
                                                            answers,
                                                            partner_rate):
    """One of the two rules the schema cannot enforce, so the prompt has to.

    Three sold and one returned have both left the original intake, so the
    intake cannot be corrected to fewer than four. A CHECK constraint cannot
    express this, because it spans three tables.
    """
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=3)
    add_return(db, 1, item_id=1, quantity=1)

    answers("jordan", "", "", "2", "5", "", "", "", "", "", "no")
    psells.edit(db)

    assert product_row(db)["quantity_received"] == 5
    assert "Value must be at least 4." in capsys.readouterr().out


def test_the_intake_floor_is_one_when_nothing_has_gone(db, capsys, answers,
                                                       partner_rate):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("jordan", "", "", "0", "1", "", "", "", "", "", "no")
    psells.edit(db)

    assert product_row(db)["quantity_received"] == 1
    assert "Value must be at least 1." in capsys.readouterr().out


def test_editing_from_an_empty_inventory(db, capsys, answers, partner_rate):
    answers()
    psells.edit(db)

    assert "Inventory is empty." in capsys.readouterr().out


def test_editing_a_product_that_does_not_match(db, capsys, answers,
                                               partner_rate):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    answers("kettle")
    psells.edit(db)

    assert "No products found." in capsys.readouterr().out


# Edit a product, part two: the partner share and the retail transitions -------
#
# Four situations, and edit treats each differently: staying at retail, going
# discontinued, staying discontinued, and coming back. Only the first offers a
# choice of mode, because a percentage of a price that no longer exists is not
# a number worth computing.

def discontinued_product(connection, amount_cents=2500):
    add_product(
        connection, 1, quantity_received=5, name="Retired Diver",
        retail_discontinued=1,
        retail_price_cents=0,
        partner_share_mode="custom_amount",
        partner_share_amount_cents=amount_cents,
    )


def test_the_current_share_is_shown_before_it_is_changed(db, capsys, answers):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago",
                partner_share_mode="custom_percent",
                partner_share_percent=35.5)

    answers("jordan", "", "", "", "", "", "", "", "", "no")
    psells.edit(db)

    printed = capsys.readouterr().out

    assert "Current partner-share mode: custom_percent" in printed
    assert "Current partner-share percentage: 35.5" in printed


def test_the_current_fixed_amount_is_shown_as_money(db, capsys, answers):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago",
                partner_share_mode="custom_amount",
                partner_share_amount_cents=2500)

    answers("jordan", "", "", "", "", "", "", "", "", "no")
    psells.edit(db)

    assert "Current partner-share amount: $25.00" in capsys.readouterr().out


def test_the_share_can_be_changed_to_a_percentage(db, answers, partner_rate):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    answers("jordan", "", "", "", "", "", "", "", "",
            "yes", "custom_percent", "30")
    psells.edit(db)

    product = product_row(db)

    assert product["partner_share_mode"] == "custom_percent"
    assert product["partner_share_percent"] == 30
    assert product["partner_share_amount_cents"] is None


def test_going_discontinued_forces_a_fixed_amount(db, answers, partner_rate):
    """No retail price is asked for and no mode is offered.

    Nine answers where the ordinary edit takes ten. The retail price question
    disappears because the price becomes zero by definition, and the mode
    question never appears because the fixed amount is the only one left.
    """
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    answers("jordan", "", "", "", "yes", "", "", "", "15.00")
    psells.edit(db)

    product = product_row(db)

    assert product["retail_discontinued"] == 1
    assert product["retail_price_cents"] == 0
    assert product["partner_share_mode"] == "custom_amount"
    assert product["partner_share_amount_cents"] == 1500
    assert product["partner_share_percent"] is None


def test_going_discontinued_leaves_an_existing_fixed_amount_alone(db, answers):
    """Already on a fixed amount, so there is nothing to ask.

    Eight answers. A partner-share question appearing here would consume one
    that is not there and fail rather than quietly changing the agreed figure.
    """
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago",
                partner_share_mode="custom_amount",
                partner_share_amount_cents=2500)

    answers("jordan", "", "", "", "yes", "", "", "")
    psells.edit(db)

    product = product_row(db)

    assert product["retail_discontinued"] == 1
    assert product["retail_price_cents"] == 0
    assert product["partner_share_amount_cents"] == 2500


def test_a_discontinued_product_can_change_its_fixed_amount(db, answers):
    discontinued_product(db)

    answers("retired", "", "", "", "", "", "", "", "yes", "30.00")
    psells.edit(db)

    product = product_row(db)

    assert product["retail_discontinued"] == 1
    assert product["partner_share_amount_cents"] == 3000


def test_coming_back_to_retail_asks_for_a_new_price(db, answers):
    """There is no previous retail price to offer, because it was zero.

    So this one question in edit has no default and no bracket, and a blank is
    not accepted. The next test covers what happens when one is given.
    """
    discontinued_product(db)

    answers("retired", "", "", "", "no", "80.00", "", "", "", "no")
    psells.edit(db)

    product = product_row(db)

    assert product["retail_discontinued"] == 0
    assert product["retail_price_cents"] == 8000
    assert product["partner_share_mode"] == "custom_amount"
    assert product["partner_share_amount_cents"] == 2500


def test_coming_back_to_retail_will_not_take_a_blank_price(db, capsys, answers):
    """The message is the generic one, which is worth knowing.

    Every other field in edit takes Enter to keep its value, so a blank here is
    a reasonable thing to try, and what comes back talks about the format of an
    amount rather than saying a price is required.
    """
    discontinued_product(db)

    answers("retired", "", "", "", "no", "", "80.00", "", "", "", "no")
    psells.edit(db)

    assert product_row(db)["retail_price_cents"] == 8000
    assert "Please enter an amount in dollars" in capsys.readouterr().out


# Out of stock and the history --------------------------------------------------
#
# Options 11 to 14, and options 2 and 4 limited to the products in stock. Each
# prints one psells function's answer; the last tests here hold the terminal
# to the API, which test_web.py holds the pages to, so all three agree.

def printed_blocks(printed):
    """What a listing printed, as one {label: value} per blank-line-separated
    block, in the order printed."""
    blocks = []
    for chunk in printed.strip("\n").split("\n\n"):
        block = {}
        for line in chunk.splitlines():
            label, value = line.split(": ", 1)
            block[label] = value
        blocks.append(block)
    return blocks


def test_inventory_lists_only_products_in_stock(db, capsys, partner_rate):
    add_shop(db)

    psells.view_inventory(db)

    assert [b["ID"] for b in printed_blocks(capsys.readouterr().out)] == [
        "1", "2"]


def test_inventory_with_everything_sold_out_says_none_in_stock(db, capsys,
                                                               partner_rate):
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1)

    psells.view_inventory(db)

    assert capsys.readouterr().out == "No products in stock.\n"


def test_search_finds_only_products_in_stock(db, capsys, answers,
                                             partner_rate):
    """"chicago" names product 1, in stock, and 3, sold out."""
    add_shop(db)

    answers("chicago")
    psells.search(db)

    assert [b["ID"] for b in printed_blocks(capsys.readouterr().out)] == ["1"]


def test_search_for_only_an_out_of_stock_product_finds_nothing(
        db, capsys, answers, partner_rate):
    add_shop(db)

    answers("hoodie")
    psells.search(db)

    assert capsys.readouterr().out == "No products in stock found.\n"


@pytest.mark.parametrize("view, message", [
    (psells.view_out_of_stock, "No products are out of stock."),
    (psells.view_sales_history, "No sales recorded yet."),
    (psells.view_returns_history, "No returns recorded yet."),
    (psells.view_payments_history, "No payments recorded yet."),
])
def test_an_empty_list_says_so(db, capsys, partner_rate, view, message):
    add_product(db, 1, quantity_received=1)

    view(db)

    assert capsys.readouterr().out == message + "\n"


def test_out_of_stock_lists_each_product_with_its_reason(db, capsys,
                                                         partner_rate):
    add_shop(db)

    psells.view_out_of_stock(db)
    blocks = printed_blocks(capsys.readouterr().out)

    assert [(b["ID"], b["Available"], b["Reason"]) for b in blocks] == [
        ("3", "0", "Sold out"), ("4", "0", "Returned"),
        ("5", "0", "2 sold, 1 returned of 3")]
    assert list(blocks[0]) == ["ID", "Name", "Category", "Available", "Reason",
                               "Listed Price", "Partner Cut", "Discontinued",
                               "Condition"]


def test_sales_history_prints_newest_first_with_its_figures(db, capsys,
                                                            partner_rate):
    add_shop(db)

    psells.view_sales_history(db)
    blocks = printed_blocks(capsys.readouterr().out)

    assert [b["Date"] for b in blocks] == ["2026-09-10", "2026-09-03",
                                           "2026-09-03"]
    assert blocks[1] == {
        "ID": "3",
        "Date": "2026-09-03", "Product": "Jordan 4 Bred", "Category": "Shoes",
        "Quantity": "2", "Price Each": "$140.00", "Sale Total": "$280.00",
        "Partner Cut": "$112.00", "Profit": "$168.00",
    }


def test_returns_history_prints_newest_first_with_notes(db, capsys,
                                                        partner_rate):
    add_shop(db)

    psells.view_returns_history(db)
    blocks = printed_blocks(capsys.readouterr().out)

    assert [(b["Product"], b["Notes"]) for b in blocks] == [
        ("Jordan 1 Chicago", "Wrong size"), ("Box Logo Hoodie", "Torn seam"),
        ("Jordan 4 Bred", "")]


def test_payments_history_prints_newest_first(db, capsys, partner_rate):
    add_shop(db)

    psells.view_payments_history(db)

    assert printed_blocks(capsys.readouterr().out) == [
        {"ID": "2", "Date": "2026-09-20", "Amount": "$123.45", "Notes": ""},
        {"ID": "3", "Date": "2026-09-15", "Amount": "$0.00",
         "Notes": "Nothing owed"},
        {"ID": "1", "Date": "2026-09-15", "Amount": "$50.00",
         "Notes": "First transfer"},
    ]


def test_the_terminal_lists_what_the_api_serves(db, capsys, client):
    add_shop(db)
    money = psells.format_cents

    def shown(view):
        view(db)
        return printed_blocks(capsys.readouterr().out)

    def product_block(p, reason=None):
        block = {"ID": str(p["id"]), "Name": p["name"],
                 "Category": p["category"],
                 "Available": str(p["quantity_available"])}
        if reason is not None:
            block["Reason"] = reason
        block.update({
            "Listed Price": money(p["listed_price_cents"]),
            "Partner Cut": money(p["partner_share_cents"]),
            "Discontinued": "Yes" if p["retail_discontinued"] else "No",
            "Condition": p["condition"]})
        return block

    assert shown(psells.view_inventory) == [
        product_block(p) for p in client.get("/products/in-stock").json()]
    assert shown(psells.view_out_of_stock) == [
        product_block(p, p["reason"])
        for p in client.get("/products/out-of-stock").json()]
    assert shown(psells.view_sales_history) == [
        {"ID": str(s["id"]), "Date": s["date"], "Product": s["name"],
         "Category": s["category"], "Quantity": str(s["quantity"]),
         "Price Each": money(s["sale_price_cents"]),
         "Sale Total": money(s["sale_total_cents"]),
         "Partner Cut": money(s["partner_cut_cents"]),
         "Profit": money(s["profit_cents"])}
        for s in client.get("/sales").json()]
    assert shown(psells.view_returns_history) == [
        {"ID": str(r["id"]), "Date": r["date"], "Product": r["name"],
         "Category": r["category"], "Quantity": str(r["quantity"]),
         "Notes": r["notes"]}
        for r in client.get("/returns").json()]
    assert shown(psells.view_payments_history) == [
        {"ID": str(p["id"]), "Date": p["date"],
         "Amount": money(p["amount_cents"]), "Notes": p["notes"]}
        for p in client.get("/payments").json()]


class Unclosed:
    """The test connection, which main() may use but not close: the db
    fixture rolls it back after the test."""

    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def close(self):
        pass


def test_the_menu_offers_and_runs_options_11_to_14(db, capsys, partner_rate,
                                                   monkeypatch):
    add_shop(db)
    monkeypatch.setattr(psells, "connect", lambda: Unclosed(db))
    replies = iter(["11", "12", "13", "14", "0"])
    prompts = []

    def answer(prompt=""):
        prompts.append(prompt)
        return next(replies)

    monkeypatch.setattr("builtins.input", answer)

    psells.main()
    printed = capsys.readouterr().out

    for line in ["2: View Inventory (in stock)", "4: Search (in stock)",
                 "11: View Out of Stock", "12: Sales History",
                 "13: Returns History", "14: Payments History",
                 "15: Fix Sale", "16: Fix Return", "17: Fix Payment"]:
        assert line in prompts[0].splitlines(), line
    assert "Reason: 2 sold, 1 returned of 3" in printed
    assert "Sale Total: $280.00" in printed
    assert "Notes: Torn seam" in printed
    assert "Notes: Nothing owed" in printed
    assert "Invalid input" not in printed


# Fixing a sale, return or payment --------------------------------------------

def corrections(db):
    return db.execute("SELECT record_type, record_id, action FROM corrections "
                      "ORDER BY id").fetchall()


def test_fixing_a_sale_by_editing_it(db, capsys, answers, partner_rate):
    """Sale 3: 2 of Jordan 4 Bred at 140.00, with a 56.00 cut frozen."""
    add_shop(db)

    answers("3", "edit", "1", "130.00", "2026-9-4")
    psells.fix_sale(db)

    printed = capsys.readouterr().out
    sale = psells.find_sale(db, 3)
    assert (sale["quantity"], sale["sale_price_cents"], str(sale["date"]),
            sale["partner_share_cents"]) == (1, 13000, "2026-09-04", 5600)
    assert "Sale updated. The sale as it was is kept in the corrections log." in (
        printed)
    assert corrections(db) == [{"record_type": "sale", "record_id": 3,
                                "action": "edit"}]


def test_pressing_enter_at_every_field_changes_nothing(db, capsys, answers,
                                                       partner_rate):
    add_shop(db)

    answers("3", "edit", "", "", "")
    psells.fix_sale(db)

    assert capsys.readouterr().out.endswith("Nothing changed.\n")
    assert corrections(db) == []


def test_a_sale_edit_past_the_stock_is_refused_with_the_reason(
        db, capsys, answers, partner_rate):
    """Product 5 has 0 available and sale 3 holds 2, so 3 is one too many."""
    add_shop(db)

    answers("3", "edit", "3", "", "")
    psells.fix_sale(db)

    assert ("Jordan 4 Bred has 0 more available, so this sale can be at most "
            "2, not 3.") in capsys.readouterr().out
    assert psells.find_sale(db, 3)["quantity"] == 2
    assert corrections(db) == []


def test_fixing_a_sale_by_deleting_it_says_what_changes(db, capsys, answers,
                                                        partner_rate):
    add_shop(db)

    answers("2", "delete", "yes")
    psells.fix_sale(db)

    printed = capsys.readouterr().out
    assert ("Deleting it gives its 2 sold back to Chicago Bulls Cap's stock, "
            "and lowers revenue by $51.00, the partner share earned by $20.40 "
            "and profit by $30.60.") in printed
    assert "Sale deleted." in printed
    assert psells.find_sale(db, 2) is None
    assert corrections(db)[0]["action"] == "delete"


def test_answering_no_keeps_the_sale(db, capsys, answers, partner_rate):
    add_shop(db)

    answers("2", "delete", "no")
    psells.fix_sale(db)

    assert "Cancelled." in capsys.readouterr().out
    assert psells.find_sale(db, 2) is not None
    assert corrections(db) == []


def test_an_id_that_names_no_sale_says_so(db, capsys, answers, partner_rate):
    add_shop(db)

    answers("99")
    psells.fix_sale(db)

    assert capsys.readouterr().out.endswith("No sale with id 99.\n")


@pytest.mark.parametrize("fix, message", [
    (psells.fix_sale, "No sales recorded yet."),
    (psells.fix_return, "No returns recorded yet."),
    (psells.fix_payment, "No payments recorded yet."),
])
def test_fixing_with_nothing_recorded_says_so_and_asks_nothing(
        db, capsys, answers, fix, message):
    answers()
    fix(db)

    assert capsys.readouterr().out == message + "\n"


def test_fixing_a_return_by_editing_then_deleting(db, capsys, answers,
                                                  partner_rate):
    add_shop(db)

    answers("1", "edit", "", "2026-02-30", "2026-09-13", "Seam repaired")
    psells.fix_return(db)
    answers("3", "delete", "yes")
    psells.fix_return(db)

    printed = capsys.readouterr().out
    assert "Please enter a valid date in YYYY-MM-DD format." in printed
    assert "No money figure changes." in printed
    edited = psells.find_return(db, 1)
    assert (str(edited["date"]), edited["notes"]) == ("2026-09-13",
                                                      "Seam repaired")
    assert psells.find_return(db, 3) is None
    assert [c["action"] for c in corrections(db)] == ["edit", "delete"]


def test_fixing_a_payment_by_editing_then_deleting(db, capsys, answers,
                                                   partner_rate):
    add_shop(db)

    answers("1", "edit", "45.00", "", "")
    psells.fix_payment(db)
    answers("2", "delete", "yes")
    psells.fix_payment(db)

    printed = capsys.readouterr().out
    assert "Payment updated." in printed
    assert ("Deleting it lowers total paid by $123.45, so the balance owing "
            "rises by the same.") in printed
    assert psells.dashboard_totals(db)["total_paid"] == 4500


def test_the_menu_runs_options_15_to_17(db, capsys, partner_rate,
                                        monkeypatch):
    add_shop(db)
    monkeypatch.setattr(psells, "connect", lambda: Unclosed(db))
    replies = iter(["15", "1", "delete", "yes",
                    "16", "2", "delete", "yes",
                    "17", "3", "delete", "yes", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))

    psells.main()

    printed = capsys.readouterr().out
    assert "Invalid input" not in printed
    assert [(c["record_type"], c["record_id"]) for c in corrections(db)] == [
        ("sale", 1), ("return", 2), ("payment", 3)]

