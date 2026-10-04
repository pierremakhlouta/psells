"""Tests for correcting a sale, return or payment: the psells functions.

Each correction changes the record and writes one row to corrections, in one
transaction. These check the rules on what may change, the stock rule, what
the dashboard does as a result, and that the log and the change are never
apart.
"""

import pytest

import psells

from helpers import add_payment, add_product, add_return, add_sale


def log(db):
    return db.execute("SELECT record_type, record_id, action, before, after "
                      "FROM corrections ORDER BY id").fetchall()


def sale(db, sale_id=1):
    return db.execute("SELECT * FROM sales WHERE id = %s",
                      (sale_id,)).fetchone()


def available(db, product_id=1):
    return db.execute("SELECT quantity_available FROM products_view "
                      "WHERE id = %s", (product_id,)).fetchone()[
        "quantity_available"]


@pytest.fixture
def a_sale(db):
    """Product 1: 10 received, a sale of 3 at 90.00 with a 35.00 cut frozen,
    so 7 available."""
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=3, sale_price_cents=9000,
             partner_share_cents=3500, date="2026-09-01")


# Sales -------------------------------------------------------------------------

def test_a_sale_edit_changes_date_quantity_and_price_and_nothing_else(db,
                                                                      a_sale):
    psells.update_sale(db, 1, 2, 8550, "2026-9-3")

    edited = sale(db)
    assert (str(edited["date"]), edited["quantity"],
            edited["sale_price_cents"]) == ("2026-09-03", 2, 8550)
    assert edited["item_id"] == 1
    assert edited["partner_share_cents"] == 3500


def test_a_sale_edit_is_logged_with_the_whole_row_before_and_after(db,
                                                                   a_sale):
    psells.update_sale(db, 1, 2, 8550, "2026-09-03")

    (entry,) = log(db)
    assert entry["record_type"] == "sale"
    assert entry["record_id"] == 1
    assert entry["action"] == "edit"
    assert entry["before"] == {
        "id": 1, "date": "2026-09-01", "item_id": 1, "quantity": 3,
        "sale_price_cents": 9000, "partner_share_cents": 3500}
    assert entry["after"] == {
        "id": 1, "date": "2026-09-03", "item_id": 1, "quantity": 2,
        "sale_price_cents": 8550, "partner_share_cents": 3500}


def test_the_partner_cut_stays_frozen_after_the_products_share_changes(
        db, a_sale):
    """The product's share is changed first. The edited sale's cut is still
    its quantity times the 35.00 frozen when it sold."""
    db.execute("UPDATE products SET partner_share_mode = 'custom_amount', "
               "partner_share_amount_cents = 100 WHERE id = 1")

    psells.update_sale(db, 1, 5, 9000, "2026-09-01")

    (row,) = psells.sales_history(db)
    assert row["partner_cut_cents"] == 5 * 3500
    assert psells.dashboard_totals(db)["total_partner_share"] == 5 * 3500


def test_a_sale_edit_moves_stock_and_the_dashboard(db, a_sale):
    add_payment(db, 1, 5000)
    psells.update_sale(db, 1, 5, 8000, "2026-09-01")

    totals = psells.dashboard_totals(db)
    assert available(db) == 5
    assert totals["total_sold"] == 5
    assert totals["total_revenue"] == 40000
    assert totals["total_partner_share"] == 17500
    assert totals["total_profit"] == 22500
    assert totals["balance_owing"] == 12500


def test_a_sale_can_grow_to_what_is_available_plus_its_own_units(db, a_sale):
    psells.update_sale(db, 1, 10, 9000, "2026-09-01")

    assert available(db) == 0


def test_a_sale_cannot_grow_past_the_stock(db, a_sale):
    with pytest.raises(psells.SaleError) as refused:
        psells.update_sale(db, 1, 11, 9000, "2026-09-01")

    assert str(refused.value) == ("Jordan 1 Chicago has 7 more available, so "
                                  "this sale can be at most 10, not 11.")
    assert sale(db)["quantity"] == 3
    assert log(db) == []


def test_the_stock_rule_counts_other_sales_and_returns(db, a_sale):
    add_sale(db, 2, item_id=1, quantity=4)
    add_return(db, 1, item_id=1, quantity=2)

    with pytest.raises(psells.SaleError):
        psells.update_sale(db, 1, 5, 9000, "2026-09-01")
    psells.update_sale(db, 1, 4, 9000, "2026-09-01")

    assert available(db) == 0


def test_a_sold_out_products_sale_can_still_shrink(db, a_sale):
    psells.update_sale(db, 1, 10, 9000, "2026-09-01")

    psells.update_sale(db, 1, 1, 9000, "2026-09-01")

    assert available(db) == 9


@pytest.mark.parametrize("quantity, price, sale_date, message", [
    (0, 9000, "2026-09-01", "Quantity must be at least 1."),
    (-1, 9000, "2026-09-01", "Quantity must be at least 1."),
    (2.5, 9000, "2026-09-01", "Quantity must be at least 1."),
    (2, -1, "2026-09-01", "Sale price cannot be negative."),
    (2, 9000, "2026-02-30", "'2026-02-30' is not a date in YYYY-MM-DD form."),
])
def test_a_sale_edit_breaking_a_rule_changes_nothing(db, a_sale, quantity,
                                                     price, sale_date,
                                                     message):
    with pytest.raises(psells.SaleError) as refused:
        psells.update_sale(db, 1, quantity, price, sale_date)

    assert str(refused.value) == message
    assert sale(db)["quantity"] == 3
    assert log(db) == []


def test_an_edit_that_changes_nothing_logs_nothing(db, a_sale):
    psells.update_sale(db, 1, 3, 9000, "2026-09-01")

    assert log(db) == []


def test_deleting_a_sale_gives_its_units_back_and_logs_the_whole_row(db,
                                                                     a_sale):
    psells.delete_sale(db, 1)

    assert sale(db) is None
    assert available(db) == 10
    assert psells.dashboard_totals(db)["total_revenue"] == 0
    (entry,) = log(db)
    assert (entry["record_type"], entry["action"]) == ("sale", "delete")
    assert entry["before"]["partner_share_cents"] == 3500
    assert entry["after"] is None


def test_a_product_whose_last_history_is_deleted_can_be_deleted(db, a_sale):
    assert psells.deletion_blocker(db, 1) is not None

    psells.delete_sale(db, 1)
    psells.delete_product(db, 1)

    # The log still holds the sale, and the product it belonged to.
    assert log(db)[0]["before"]["item_id"] == 1


@pytest.mark.parametrize("correct", [
    lambda db: psells.update_sale(db, 99, 1, 9000, "2026-09-01"),
    lambda db: psells.delete_sale(db, 99),
])
def test_a_sale_that_does_not_exist_is_its_own_refusal(db, a_sale, correct):
    with pytest.raises(psells.SaleNotFound) as refused:
        correct(db)

    assert str(refused.value) == "No sale with id 99."
    assert isinstance(refused.value, psells.SaleError)
    assert log(db) == []


# Returns -----------------------------------------------------------------------

@pytest.fixture
def a_return(db):
    """Product 1: 5 received, 2 returned, so 3 available."""
    add_product(db, 1, quantity_received=5, name="Box Logo Hoodie")
    add_return(db, 1, item_id=1, quantity=2, date="2026-09-05",
               notes="Torn seam")


def test_a_return_edit_changes_quantity_date_and_notes(db, a_return):
    psells.update_return(db, 1, 5, "2026-09-06", "  Both torn  ")

    row = psells.find_return(db, 1)
    assert (row["quantity"], str(row["date"]), row["notes"]) == (
        5, "2026-09-06", "Both torn")
    assert row["item_id"] == 1
    assert available(db) == 0
    (entry,) = log(db)
    assert entry["before"]["notes"] == "Torn seam"
    assert entry["after"]["notes"] == "Both torn"


def test_a_return_cannot_grow_past_the_stock(db, a_return):
    with pytest.raises(psells.ReturnError) as refused:
        psells.update_return(db, 1, 6, "2026-09-05", "Torn seam")

    assert "can be at most 5, not 6" in str(refused.value)
    assert log(db) == []


def test_deleting_a_return_gives_its_units_back(db, a_return):
    psells.delete_return(db, 1)

    assert psells.find_return(db, 1) is None
    assert available(db) == 5
    assert log(db)[0]["action"] == "delete"


def test_a_return_that_does_not_exist_is_its_own_refusal(db, a_return):
    with pytest.raises(psells.ReturnNotFound):
        psells.update_return(db, 99, 1, "2026-09-05", "")
    with pytest.raises(psells.ReturnNotFound):
        psells.delete_return(db, 99)


# Payments ----------------------------------------------------------------------

@pytest.fixture
def a_payment(db):
    add_payment(db, 1, 5000, "First transfer", date="2026-09-15")


def test_a_payment_edit_changes_amount_date_and_notes(db, a_payment):
    psells.update_payment(db, 1, 4500, "2026-09-16", "Corrected amount")

    row = psells.find_payment(db, 1)
    assert (row["amount_cents"], str(row["date"]), row["notes"]) == (
        4500, "2026-09-16", "Corrected amount")
    assert psells.dashboard_totals(db)["total_paid"] == 4500
    assert log(db)[0]["after"]["amount_cents"] == 4500


def test_a_payment_can_be_corrected_to_zero_but_not_below(db, a_payment):
    psells.update_payment(db, 1, 0, "2026-09-15", "")

    with pytest.raises(psells.PaymentError) as refused:
        psells.update_payment(db, 1, -1, "2026-09-15", "")

    assert str(refused.value) == "Amount cannot be negative."
    assert psells.find_payment(db, 1)["amount_cents"] == 0


def test_deleting_a_payment_lowers_total_paid(db, a_payment):
    psells.delete_payment(db, 1)

    assert psells.dashboard_totals(db)["total_paid"] == 0
    assert log(db)[0]["before"]["amount_cents"] == 5000


def test_a_payment_that_does_not_exist_is_its_own_refusal(db, a_payment):
    with pytest.raises(psells.PaymentNotFound):
        psells.update_payment(db, 99, 1, "2026-09-15", "")
    with pytest.raises(psells.PaymentNotFound):
        psells.delete_payment(db, 99)


# One transaction ---------------------------------------------------------------

@pytest.mark.parametrize("correct", [
    lambda db: psells.update_sale(db, 1, 2, 9000, "2026-09-01"),
    lambda db: psells.delete_sale(db, 1),
])
def test_a_change_whose_log_fails_is_undone(db, a_sale, monkeypatch,
                                            correct):
    def broken_log(*args, **kwargs):
        raise RuntimeError("the log could not be written")

    monkeypatch.setattr(psells, "_log_correction", broken_log)

    with pytest.raises(RuntimeError):
        correct(db)

    assert sale(db)["quantity"] == 3


# From a form's text ------------------------------------------------------------

def test_saving_each_edit_form_unchanged_changes_nothing(db, a_sale):
    add_return(db, 1, item_id=1, quantity=1, date="2026-09-05", notes="Scuff")
    add_payment(db, 1, 123456, "Big one", date="2026-09-15")

    psells.update_sale_from_text(db, 1, psells.sale_form_text(
        psells.find_sale(db, 1)))
    psells.update_return_from_text(db, 1, psells.return_form_text(
        psells.find_return(db, 1)))
    psells.update_payment_from_text(db, 1, psells.payment_form_text(
        psells.find_payment(db, 1)))

    assert log(db) == []


def test_an_edit_form_is_read_as_the_entry_form_is(db, a_sale):
    psells.update_sale_from_text(db, 1, {"quantity": " 2 ",
                                         "sale_price": "85.50",
                                         "date": "2026-9-3"})

    edited = sale(db)
    assert (edited["quantity"], edited["sale_price_cents"],
            str(edited["date"])) == (2, 8550, "2026-09-03")


def test_wrong_text_is_refused_field_by_field_and_changes_nothing(db,
                                                                  a_sale):
    with pytest.raises(psells.SaleInputError) as refused:
        psells.update_sale_from_text(db, 1, {"quantity": "two",
                                             "sale_price": "abc",
                                             "date": "soon"})

    assert set(refused.value.problems) == {"quantity", "sale_price", "date"}
    assert sale(db)["quantity"] == 3
    assert log(db) == []


def test_return_and_payment_text_is_refused_field_by_field(db, a_sale):
    add_return(db, 1, item_id=1, quantity=1)
    add_payment(db, 1, 100)

    with pytest.raises(psells.ReturnInputError) as return_refused:
        psells.update_return_from_text(db, 1, {"quantity": "0", "date": "x"})
    with pytest.raises(psells.PaymentInputError) as payment_refused:
        psells.update_payment_from_text(db, 1, {"amount": "-5", "date": ""})

    assert set(return_refused.value.problems) == {"quantity", "date"}
    assert set(payment_refused.value.problems) == {"amount"}
    assert log(db) == []


def test_one_record_reads_as_its_row_in_the_history(db, a_sale):
    add_return(db, 1, item_id=1, quantity=1)
    add_payment(db, 1, 100)

    assert psells.find_sale(db, 1) == psells.sales_history(db)[0]
    assert psells.find_return(db, 1) == psells.returns_history(db)[0]
    assert psells.find_payment(db, 1) == psells.payments_history(db)[0]
    assert psells.find_sale(db, 99) is None
