"""End-to-end tests of the functions that prompt and print.

These call the feature functions the way the menu does, with input faked and
output captured, and check what the user would actually see. test_domain.py
covers the calculations underneath; a failure here means the application is
wrong rather than the arithmetic.

They assert on particular facts rather than on whole blocks of output, so
rewording a heading does not fail a test that nothing broke.
"""

from datetime import date

import psells

from helpers import add_payment, add_product, add_return, add_sale


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

    This records what the application prints today, sign placement included.
    """
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1,
             sale_price_cents=2000, partner_share_cents=500)
    add_payment(db, 1, amount_cents=800)

    psells.view_dashboard(db)

    assert "Balance owing: $-3.00" in capsys.readouterr().out


def test_inventory_says_so_when_it_is_empty(db, capsys):
    psells.view_inventory(db)

    assert "Inventory is empty." in capsys.readouterr().out


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

    Without ORDER BY, SQLite makes no promise at all. It would happen to come
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

    assert "No products found." in capsys.readouterr().out


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

    assert payment["date"] == "2026-09-14"
    assert payment["amount_cents"] == 15000
    assert payment["notes"] == "e-transfer"
    assert "Payment recorded." in capsys.readouterr().out


def test_a_blank_date_means_today(db, capsys, answers):
    answers("", "50", "")
    psells.record_payment(db)

    assert only_payment(db)["date"] == date.today().isoformat()


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

    assert only_payment(db)["date"] == "2026-09-14"
    assert "Please enter a valid date in YYYY-MM-DD format." in capsys.readouterr().out
