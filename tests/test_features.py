"""End-to-end tests of the functions that prompt and print.

These call the feature functions the way the menu does, with input faked and
output captured, and check what the user would actually see. test_domain.py
covers the calculations underneath; a failure here means the application is
wrong rather than the arithmetic.

They assert on particular facts rather than on whole blocks of output, so
rewording a heading does not fail a test that nothing broke.
"""

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
