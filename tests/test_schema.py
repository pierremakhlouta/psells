"""Tests for schema_postgres.sql, run against a real PostgreSQL.

Each rule the schema carries is tried with a row that breaks exactly that
rule, and the refusal must name the constraint that was meant to catch it. A
test that accepted any refusal would pass for the wrong reason: a row broken in
two ways is refused by whichever check runs first.

The control test matters as much as the refusals. Every bad row is the good
row with one field changed, so the good row being accepted is what shows each
refusal is about that one field.
"""

import datetime

import psycopg
import pytest
from psycopg import errors

from helpers import TEST_DATABASE_URL


GOOD_PRODUCT = {
    "category": "Watches",
    "name": "Field Watch",
    "quantity_received": 3,
    "retail_price_cents": 20000,
    "listed_price_cents": 14000,
    "retail_discontinued": 0,
    "partner_share_mode": "default",
    "partner_share_percent": None,
    "partner_share_amount_cents": None,
    "condition": "Brand New",
    "notes": "",
}


def insert_product(pg, **changes):
    row = GOOD_PRODUCT | changes
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    return pg.execute(
        f"INSERT INTO products ({columns}) VALUES ({placeholders}) RETURNING id",
        list(row.values()),
    ).fetchone()["id"]


def insert_sale(pg, item_id, quantity=1, date="2026-05-14",
                sale_price_cents=15000, partner_share_cents=6000):
    return pg.execute(
        "INSERT INTO sales (date, item_id, quantity, sale_price_cents, "
        "partner_share_cents) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (date, item_id, quantity, sale_price_cents, partner_share_cents),
    ).fetchone()["id"]


def insert_return(pg, item_id, quantity=1, date="2026-06-30"):
    return pg.execute(
        "INSERT INTO returns (date, item_id, quantity, notes) "
        "VALUES (%s, %s, %s, '') RETURNING id",
        (date, item_id, quantity),
    ).fetchone()["id"]


def refused(pg, statement, parameters=()):
    """Run a statement that must fail, and hand back the error it raised."""
    with pytest.raises(errors.IntegrityError) as caught:
        with pg.transaction():
            pg.execute(statement, parameters)
    return caught.value


# Products --------------------------------------------------------------------

def test_the_good_product_is_accepted(pg):
    product_id = insert_product(pg)

    row = pg.execute("SELECT * FROM products WHERE id = %s",
                     (product_id,)).fetchone()
    assert row["name"] == "Field Watch"


@pytest.mark.parametrize("changes, constraint", [
    ({"category": "   "}, "products_category_check"),
    ({"name": ""}, "products_name_check"),
    ({"quantity_received": 0}, "products_quantity_received_check"),
    ({"retail_price_cents": -1}, "products_retail_price_cents_check"),
    ({"listed_price_cents": -1}, "products_listed_price_cents_check"),
    ({"retail_discontinued": 2}, "products_retail_discontinued_check"),
    ({"condition": " "}, "products_condition_check"),
    ({"partner_share_mode": "custom_amount",
      "partner_share_amount_cents": -1},
     "products_partner_share_amount_cents_check"),
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": 100.5},
     "products_partner_share_percent_check"),
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": -0.5},
     "products_partner_share_percent_check"),
    # PostgreSQL sorts NaN above every number, so the range refuses it.
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": float("nan")},
     "products_partner_share_percent_check"),
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": float("inf")},
     "products_partner_share_percent_check"),
    # Each mode allows exactly one shape.
    ({"partner_share_percent": 40.0}, "partner_share_matrix"),
    ({"partner_share_amount_cents": 500}, "partner_share_matrix"),
    ({"partner_share_mode": "custom_percent"}, "partner_share_matrix"),
    ({"partner_share_mode": "custom_amount"}, "partner_share_matrix"),
    ({"partner_share_mode": "custom_amount",
      "partner_share_amount_cents": 500,
      "partner_share_percent": 40.0}, "partner_share_matrix"),
    # A discontinued product has no retail price and a fixed partner amount;
    # a current one has a retail price.
    ({"retail_price_cents": 0}, "retail_discontinued_rules"),
    ({"retail_discontinued": 1, "partner_share_mode": "custom_amount",
      "partner_share_amount_cents": 500}, "retail_discontinued_rules"),
    ({"retail_discontinued": 1, "retail_price_cents": 0},
     "retail_discontinued_rules"),
])
def test_a_product_breaking_one_rule_is_refused_by_that_rule(
        pg, changes, constraint):
    row = GOOD_PRODUCT | changes

    error = refused(
        pg,
        f"INSERT INTO products ({', '.join(row)}) "
        f"VALUES ({', '.join(['%s'] * len(row))})",
        list(row.values()),
    )

    assert error.diag.constraint_name == constraint


def test_an_unknown_partner_share_mode_is_refused(pg):
    # No row can pass partner_share_matrix with an unknown mode, so which of
    # the two constraints reports it is PostgreSQL's choice. Either is right.
    row = GOOD_PRODUCT | {"partner_share_mode": "sometimes"}

    error = refused(
        pg,
        f"INSERT INTO products ({', '.join(row)}) "
        f"VALUES ({', '.join(['%s'] * len(row))})",
        list(row.values()),
    )

    assert error.diag.constraint_name in (
        "partner_share_mode_valid", "partner_share_matrix")


@pytest.mark.parametrize("column", [
    "category", "name", "quantity_received", "retail_price_cents",
    "listed_price_cents", "retail_discontinued", "partner_share_mode",
    "condition", "notes",
])
def test_a_required_product_column_cannot_be_null(pg, column):
    row = GOOD_PRODUCT | {column: None}

    with pytest.raises(errors.NotNullViolation):
        with pg.transaction():
            insert_product(pg, **row)


def test_a_discontinued_product_with_a_fixed_amount_is_accepted(pg):
    product_id = insert_product(
        pg, retail_discontinued=1, retail_price_cents=0,
        partner_share_mode="custom_amount", partner_share_amount_cents=9000)

    assert product_id > 0


def test_money_beyond_an_integer_is_refused_rather_than_wrapped(pg):
    with pytest.raises(errors.NumericValueOutOfRange):
        with pg.transaction():
            insert_product(pg, retail_price_cents=2**31)


# Ids -------------------------------------------------------------------------

def test_an_insert_cannot_choose_its_own_id(pg):
    row = GOOD_PRODUCT | {"id": 999}

    with pytest.raises(errors.GeneratedAlways):
        with pg.transaction():
            pg.execute(
                f"INSERT INTO products ({', '.join(row)}) "
                f"VALUES ({', '.join(['%s'] * len(row))})",
                list(row.values()),
            )


def test_an_id_is_never_reused_after_the_newest_product_is_deleted(pg):
    deleted = insert_product(pg, name="Deleted")
    pg.execute("DELETE FROM products WHERE id = %s", (deleted,))

    added_after = insert_product(pg, name="Added after")

    assert added_after > deleted


# Sales, returns and payments -------------------------------------------------

@pytest.mark.parametrize("changes, constraint", [
    ({"quantity": 0}, "sales_quantity_check"),
    ({"sale_price_cents": -1}, "sales_sale_price_cents_check"),
    ({"partner_share_cents": -1}, "sales_partner_share_cents_check"),
])
def test_a_sale_breaking_one_rule_is_refused_by_that_rule(
        pg, changes, constraint):
    product_id = insert_product(pg)

    with pytest.raises(errors.CheckViolation) as caught:
        with pg.transaction():
            insert_sale(pg, product_id, **changes)

    assert caught.value.diag.constraint_name == constraint


def test_a_return_of_no_units_is_refused(pg):
    product_id = insert_product(pg)

    with pytest.raises(errors.CheckViolation) as caught:
        with pg.transaction():
            insert_return(pg, product_id, quantity=0)

    assert caught.value.diag.constraint_name == "returns_quantity_check"


def test_a_negative_payment_is_refused(pg):
    error = refused(
        pg,
        "INSERT INTO payments (date, amount_cents, notes) "
        "VALUES ('2026-06-05', -1, '')",
    )

    assert error.diag.constraint_name == "payments_amount_cents_check"


@pytest.mark.parametrize("table, statement", [
    ("sales",
     "INSERT INTO sales (date, item_id, quantity, sale_price_cents, "
     "partner_share_cents) VALUES ('2026-05-14', %s, 1, 100, 40)"),
    ("returns",
     "INSERT INTO returns (date, item_id, quantity, notes) "
     "VALUES ('2026-05-14', %s, 1, '')"),
])
def test_a_row_for_a_product_that_does_not_exist_is_refused(
        pg, table, statement):
    missing = insert_product(pg)
    pg.execute("DELETE FROM products WHERE id = %s", (missing,))

    error = refused(pg, statement, (missing,))

    assert isinstance(error, errors.ForeignKeyViolation)
    assert error.diag.constraint_name == f"{table}_item_id_fkey"


@pytest.mark.parametrize("record, table", [
    (insert_sale, "sales"),
    (insert_return, "returns"),
])
def test_a_product_with_history_cannot_be_deleted(pg, record, table):
    product_id = insert_product(pg)
    record(pg, product_id)

    error = refused(pg, "DELETE FROM products WHERE id = %s", (product_id,))

    # The class of error depends on the version: PostgreSQL 18 reports ON
    # DELETE RESTRICT as RestrictViolation, 16 as ForeignKeyViolation. Both
    # are integrity errors, and both name the key that refused, which is what
    # the rule is about.
    assert error.diag.constraint_name == f"{table}_item_id_fkey"


@pytest.mark.parametrize("text", ["2026-02-30", "2026-13-01", "not a date"])
def test_an_impossible_date_is_refused_by_the_type(pg, text):
    product_id = insert_product(pg)

    with pytest.raises(errors.DataError):
        with pg.transaction():
            insert_sale(pg, product_id, date=text)


def test_a_date_is_stored_as_a_date_whatever_its_padding(pg):
    # SQLite checked text, so 2026-9-3 was refused and create_sale had to pad
    # it (31.4). The DATE type stores a day, not the characters it was
    # written with.
    product_id = insert_product(pg)
    sale_id = insert_sale(pg, product_id, date="2026-9-3")

    stored = pg.execute("SELECT date FROM sales WHERE id = %s",
                        (sale_id,)).fetchone()["date"]

    assert stored == datetime.date(2026, 9, 3)


# The view and the types Python receives --------------------------------------

def test_the_view_derives_stock_without_multiplying_sales_by_returns(pg):
    # Two sales and three returns: joined naively they would make six rows
    # and every sum would be wrong.
    product_id = insert_product(pg, quantity_received=10)
    insert_sale(pg, product_id, quantity=2)
    insert_sale(pg, product_id, quantity=1)
    insert_return(pg, product_id, quantity=1)
    insert_return(pg, product_id, quantity=1)
    insert_return(pg, product_id, quantity=2)

    rows = pg.execute("SELECT * FROM products_view WHERE id = %s",
                      (product_id,)).fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row["quantity_sold"] == 3
    assert row["quantity_returned"] == 4
    assert row["quantity_available"] == 3


def test_a_product_with_no_history_shows_zero_not_null(pg):
    product_id = insert_product(pg)

    row = pg.execute("SELECT * FROM products_view WHERE id = %s",
                     (product_id,)).fetchone()

    assert (row["quantity_sold"], row["quantity_returned"],
            row["quantity_available"]) == (0, 0, 3)


def test_python_receives_the_types_the_application_expects(pg):
    # A third: a percentage whose float needs all of its digits.
    percent = 100 / 3
    product_id = insert_product(pg, partner_share_mode="custom_percent",
                                partner_share_percent=percent)
    insert_sale(pg, product_id)

    product = pg.execute("SELECT * FROM products_view WHERE id = %s",
                         (product_id,)).fetchone()
    revenue = pg.execute(
        "SELECT COALESCE(SUM(quantity * sale_price_cents), 0) AS total "
        "FROM sales").fetchone()["total"]
    sale_date = pg.execute("SELECT date FROM sales").fetchone()["date"]

    # A percentage reads back as exactly the float that went in, as SQLite's
    # REAL did. PostgreSQL's four-byte real keeps about seven significant
    # digits and would give back 33.333332. A short value such as 12.3 would
    # not show the difference, which is why this one is long.
    assert type(product["partner_share_percent"]) is float
    assert product["partner_share_percent"] == percent
    # Money and quantities are int, sums included. A bigint column would sum
    # to Decimal.
    assert type(product["retail_price_cents"]) is int
    assert type(product["quantity_available"]) is int
    assert type(revenue) is int
    assert type(product["retail_discontinued"]) is int
    assert type(sale_date) is datetime.date


# Isolation -------------------------------------------------------------------

def test_a_transaction_block_in_a_test_does_not_commit(pg):
    # pg.transaction() commits when it opens a transaction of its own, and is
    # a savepoint only inside one that is already open. The fixture opens one
    # first so that a block like this, even as a test's first statement, can
    # never commit. A second connection sees only what was committed.
    with pg.transaction():
        pg.execute("INSERT INTO payments (date, amount_cents, notes) "
                   "VALUES ('2026-06-05', 100, 'must not be committed')")

    with psycopg.connect(TEST_DATABASE_URL) as other:
        seen = other.execute(
            "SELECT COUNT(*) FROM payments "
            "WHERE notes = 'must not be committed'").fetchone()[0]

    assert seen == 0


def test_every_test_starts_with_empty_tables(pg):
    # Last in the file on purpose: every test above has written rows, and each
    # one's rollback is what leaves these tables empty. If the fixture ever
    # committed instead, this is the test that would say so.
    for table in ("products", "sales", "returns", "payments"):
        count = pg.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        assert count["n"] == 0, table
