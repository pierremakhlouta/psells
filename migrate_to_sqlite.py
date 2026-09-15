"""One-time migration of the PSells JSON data files into SQLite.

Run once, from the project root:

    python3 migrate_to_sqlite.py

It reads data/*.json, creates data/psells.db, and verifies the result against
the figures the current application produces. It never modifies or deletes the
JSON files: those stay in place as a fallback until the rewrite is finished.

Like the Excel importer before it, this builds everything in memory, writes all
of it or none of it, and refuses to run against a database that already exists.
"""

import json
import os
import sqlite3
import sys
from decimal import Decimal, ROUND_HALF_UP

import psells


DB_FILE = "data/psells.db"
SCHEMA_FILE = "schema.sql"

INVENTORY_FILE = "data/inventory.json"
SALES_FILE = "data/sales.json"
RETURNS_FILE = "data/returns.json"
PAYMENTS_FILE = "data/payments.json"


# Conversion ----------------------------------------------------------------

def to_cents(dollars):
    """Convert a dollar figure to a whole number of cents, rounding half up.

    Decimal(str(x)) is deliberate. Going through the text form of the float
    avoids inheriting the binary error: str(26.099999999999998) keeps the
    digits, and the decimal arithmetic that follows is exact.

    round() is not used because Python rounds half to even, so round(0.125, 2)
    gives 0.12. Half away from zero is the convention people expect when money
    is being settled between two parties.
    """
    return int(
        (Decimal(str(dollars)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def product_row(product):
    """Turn one JSON product into a row for the products table.

    Three shape changes happen here:

      quantity_sold is dropped. It is now derived from the sales table.
      discontinued becomes retail_discontinued, stored as 0 or 1.
      partner_share_value splits into a percentage column and an amount column,
      with only the one matching the mode filled in and the other left NULL.
    """
    mode = product["partner_share_mode"]
    value = product.get("partner_share_value")

    percent = value if mode == "custom_percent" else None
    amount_cents = to_cents(value) if mode == "custom_amount" else None

    return (
        product["id"],
        product["category"],
        product["name"],
        product["quantity_received"],
        to_cents(product["retail_price"]),
        to_cents(product["listed_price"]),
        1 if product.get("discontinued", False) else 0,
        mode,
        percent,
        amount_cents,
        product["condition"],
        product.get("notes") or "",
    )


def sale_row(sale):
    return (
        sale["id"],
        sale["date"],
        sale["item_id"],
        sale["quantity"],
        to_cents(sale["sale_price"]),
        to_cents(sale["partner_share"]),
    )


def return_row(record):
    return (
        record["id"],
        record["date"],
        record["item_id"],
        record["quantity"],
        record.get("notes") or "",
    )


def payment_row(payment):
    return (
        payment["id"],
        payment["date"],
        to_cents(payment["amount"]),
        payment.get("notes") or "",
    )


# Writing -------------------------------------------------------------------

def insert_all(connection, table, columns, rows, source_records):
    """Insert every row, naming the offending record if one is refused.

    The rows go in one at a time rather than with executemany, purely so that a
    constraint failure can say which record caused it. "CHECK constraint failed:
    retail_discontinued_rules" is not much help when there are 263 products.

    The exception is re-raised after reporting, so the surrounding transaction
    rolls the whole thing back. Nothing is committed here.
    """
    placeholders = ", ".join("?" for _ in columns)
    statement = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    )

    for row, record in zip(rows, source_records):
        try:
            connection.execute(statement, row)
        except sqlite3.Error as error:
            print(
                f"  refused by the database: {table} record id "
                f"{record.get('id', '?')}: {error}"
            )
            raise


# Verification --------------------------------------------------------------
#
# Deliberately prints whether each figure matches, never the figure itself.
# The output of this script is meant to be safe to paste anywhere, and revenue,
# partner share and balance owing are real business figures.

def database_totals(connection):
    """The nine dashboard figures, computed from the database, in cents."""
    def one(sql):
        return connection.execute(sql).fetchone()[0]

    received = one("SELECT COALESCE(SUM(quantity_received), 0) FROM products")
    sold = one("SELECT COALESCE(SUM(quantity), 0) FROM sales")
    returned = one("SELECT COALESCE(SUM(quantity), 0) FROM returns")

    revenue = one(
        "SELECT COALESCE(SUM(quantity * sale_price_cents), 0) FROM sales"
    )
    partner_share = one(
        "SELECT COALESCE(SUM(quantity * partner_share_cents), 0) FROM sales"
    )
    paid = one("SELECT COALESCE(SUM(amount_cents), 0) FROM payments")

    return {
        "total_received": received,
        "total_sold": sold,
        "total_returned": returned,
        "total_available": received - sold - returned,
        "total_revenue": revenue,
        "total_partner_share": partner_share,
        "total_profit": revenue - partner_share,
        "total_paid": paid,
        "balance_owing": partner_share - paid,
    }


def verify(connection, inventory, sales, returns, payments):
    """Compare the database against the current application. Returns True if
    every check passes."""
    ok = True

    print("Row counts")
    for table, source in (
        ("products", inventory),
        ("sales", sales),
        ("returns", returns),
        ("payments", payments),
    ):
        in_db = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        match = in_db == len(source)
        ok = ok and match
        print(f"  {table:9} json {len(source):4}  database {in_db:4}  "
              f"{'match' if match else 'MISMATCH'}")

    # The migration drops the stored quantity_sold. This proves nothing was lost
    # by checking every product's derived figure against the number that used to
    # be stored, rather than trusting that they agree.
    print()
    print("Derived quantity_sold against the figure that used to be stored")
    derived = dict(
        connection.execute("SELECT id, quantity_sold FROM products_view")
    )
    disagreements = [
        product["id"]
        for product in inventory
        if derived.get(product["id"], 0) != product["quantity_sold"]
    ]
    if disagreements:
        ok = False
        print(f"  {len(disagreements)} products disagree, ids: {disagreements[:10]}")
    else:
        print(f"  all {len(inventory)} products agree")

    # The figures the live application produces today, converted to cents so the
    # comparison is exact rather than within a tolerance.
    print()
    print("Dashboard figures")
    before = psells.dashboard_totals(inventory, sales, returns, payments)
    after = database_totals(connection)

    quantity_keys = (
        "total_received", "total_sold", "total_returned", "total_available"
    )
    money_keys = (
        "total_revenue", "total_partner_share", "total_profit",
        "total_paid", "balance_owing"
    )

    for key in quantity_keys:
        expected = before[key]
        # total_available changed definition: returns used to be subtracted from
        # quantity_received before the dashboard ever saw it, and now they are
        # subtracted here instead. With no returns recorded the two agree.
        if key == "total_available":
            expected = before[key] - before["total_returned"]
        match = expected == after[key]
        ok = ok and match
        print(f"  {key:22} {'match' if match else 'MISMATCH'}")

    for key in money_keys:
        expected = to_cents(before[key])
        match = expected == after[key]
        ok = ok and match
        note = "" if match else f"  (differs by {after[key] - expected} cents)"
        print(f"  {key:22} {'match' if match else 'MISMATCH'}{note}")

    return ok


# Entry point ---------------------------------------------------------------

def main():
    if os.path.exists(DB_FILE):
        # sqlite3.connect() creates a database rather than complaining about a
        # missing one, so without this check a second run would append to, or
        # collide with, whatever is already there.
        print(f"{DB_FILE} already exists. Refusing to run.")
        print("Move it aside first if you really mean to migrate again.")
        sys.exit(1)

    if not os.path.exists(SCHEMA_FILE):
        print(f"{SCHEMA_FILE} not found. Run this from the project root.")
        sys.exit(1)

    inventory = psells.load_data(INVENTORY_FILE)
    sales = psells.load_data(SALES_FILE)
    returns = psells.load_data(RETURNS_FILE)
    payments = psells.load_data(PAYMENTS_FILE)

    if not inventory:
        print("No inventory found. Run this from the project root.")
        sys.exit(1)

    print(f"Read {len(inventory)} products, {len(sales)} sales, "
          f"{len(returns)} returns, {len(payments)} payments.")

    # Every conversion happens here, before the database is touched at all, so a
    # bad value fails before anything has been created.
    product_rows = [product_row(p) for p in inventory]
    sale_rows = [sale_row(s) for s in sales]
    return_rows = [return_row(r) for r in returns]
    payment_rows = [payment_row(p) for p in payments]

    connection = sqlite3.connect(DB_FILE)

    try:
        # First statement on the connection, before any transaction opens,
        # because the pragma is silently ignored inside one.
        connection.execute("PRAGMA foreign_keys = ON")

        with open(SCHEMA_FILE) as schema:
            connection.executescript(schema.read())

        # One transaction around every insert. If any row is refused, the whole
        # thing rolls back and the database is left empty rather than half full.
        with connection:
            insert_all(
                connection, "products",
                ["id", "category", "name", "quantity_received",
                 "retail_price_cents", "listed_price_cents",
                 "retail_discontinued", "partner_share_mode",
                 "partner_share_percent", "partner_share_amount_cents",
                 "condition", "notes"],
                product_rows, inventory
            )
            insert_all(
                connection, "sales",
                ["id", "date", "item_id", "quantity",
                 "sale_price_cents", "partner_share_cents"],
                sale_rows, sales
            )
            insert_all(
                connection, "returns",
                ["id", "date", "item_id", "quantity", "notes"],
                return_rows, returns
            )
            insert_all(
                connection, "payments",
                ["id", "date", "amount_cents", "notes"],
                payment_rows, payments
            )

        print("Inserted and committed.")
        print()

        if verify(connection, inventory, sales, returns, payments):
            print()
            print("Every check passed.")
        else:
            print()
            print("At least one check FAILED. The database is written but must "
                  "not be trusted. Delete it and investigate.")
            sys.exit(1)

    except Exception as error:
        connection.close()
        # Nothing was committed, but the file itself was created by connect(),
        # so remove it rather than leaving an empty database that a later run
        # would refuse to overwrite.
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        print(f"Migration failed, nothing was written: {error}")
        sys.exit(1)

    connection.close()


if __name__ == "__main__":
    main()
