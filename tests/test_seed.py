"""Tests for sample_data/seed.sql, the invented records the demo shows.

The seed is what the AWS server and the psells-sample stack load, and what any
screenshot is taken from, so it has to show every list with something in it
and has to obey the same rules as records entered through the application.
These load it into the test database, inside the test's transaction, and read
it back through the psells functions the pages use.
"""

import os
import re
from collections import Counter

import pytest

import psells


SEED = os.path.join(psells.PROJECT_DIR, "sample_data", "seed.sql")
SAMPLE_CONFIG = os.path.join(psells.PROJECT_DIR, "sample_data", "config.json")


@pytest.fixture
def seeded(db, monkeypatch):
    """The test database with the seed loaded, and the sample configuration's
    placeholder percentage as the default partner share.

    BEGIN and COMMIT are left out, so the rows stay in the db fixture's
    transaction and are rolled back with it.
    """
    with open(SEED) as file:
        text = file.read()
    statements = [s.strip() for s in text.split(";\n")]
    for statement in statements:
        statement = re.sub(r"^--.*$", "", statement, flags=re.M).strip()
        if statement and statement not in ("BEGIN", "COMMIT", "COMMIT;"):
            db.execute(statement)
    monkeypatch.setattr(psells, "CONFIG_FILE", SAMPLE_CONFIG)
    return db


def ids(rows):
    return [row["id"] for row in rows]


def test_the_seed_is_one_transaction():
    with open(SEED) as file:
        lines = [line for line in file.read().splitlines()
                 if line and not line.startswith("--")]

    assert lines[0] == "BEGIN;"
    assert lines[-1] == "COMMIT;"


def test_products_in_stock_include_two_glasses_a_search_finds(seeded):
    in_stock = psells.in_stock_products(seeded)
    glasses = psells.find_items_by_name_or_category(in_stock, "glasses")

    assert ids(in_stock) == [1, 3, 4, 5, 6, 7]
    assert len(glasses) == 2
    assert all("glasses" in row["name"].lower() for row in glasses)


def test_one_product_out_of_stock_for_each_reason(seeded):
    reasons = {row["id"]: psells.out_of_stock_reason(row)
               for row in psells.out_of_stock_products(seeded)}

    assert reasons == {2: "Sold out", 8: "Returned",
                       9: "2 sold, 1 returned of 3"}


def test_the_sales_show_a_shared_date_and_more_than_one_unit(seeded):
    sales = psells.sales_history(seeded)
    dates = Counter(sale["date"] for sale in sales)

    assert len(dates) >= 4
    assert max(dates.values()) == 2
    assert any(sale["quantity"] > 1 for sale in sales)


def test_the_sales_cover_every_partner_share_mode(seeded):
    modes = {row["partner_share_mode"]
             for row in psells.all_products(seeded)
             if row["quantity_sold"] > 0}

    assert modes == {"default", "custom_percent", "custom_amount"}


def test_each_sale_froze_the_cut_its_product_gives(seeded):
    """As create_sale would have: today's partner_share_for, which the seed's
    products have not been edited away from, on the sample percentage."""
    products = {row["id"]: row for row in psells.all_products(seeded)}

    for sale in psells.sales_history(seeded):
        assert sale["partner_share_cents"] == psells.partner_share_for(
            products[sale["item_id"]]), sale["id"]


def test_every_sale_makes_a_profit(seeded):
    for sale in psells.sales_history(seeded):
        assert sale["profit_cents"] > 0, sale["id"]


def test_the_returns_have_notes_and_different_dates(seeded):
    returns = psells.returns_history(seeded)

    assert len(returns) >= 2
    assert all(row["notes"] for row in returns)
    assert len({row["date"] for row in returns}) == len(returns)


def test_there_are_at_least_three_payments_and_some_is_still_owed(seeded):
    payments = psells.payments_history(seeded)
    totals = psells.dashboard_totals(seeded)

    assert len(payments) >= 3
    assert totals["balance_owing"] > 0


def test_nothing_is_sold_or_returned_beyond_what_was_received(seeded):
    """The application refuses it; a seed written by hand could not be."""
    for row in psells.all_products(seeded):
        assert row["quantity_available"] >= 0, row["id"]


def test_the_next_row_of_each_kind_gets_the_id_after_the_seed(seeded):
    for table in ["products", "sales", "returns", "payments"]:
        row = seeded.execute(
            f"SELECT max(id) AS highest, pg_sequence_last_value("
            f"pg_get_serial_sequence('{table}', 'id')::regclass) AS last "
            f"FROM {table}").fetchone()

        assert row["last"] == row["highest"], table
