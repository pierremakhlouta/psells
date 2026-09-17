"""Row builders shared by the test files.

These live here rather than in conftest.py because they are ordinary functions
rather than fixtures, so a test file imports them by name. pytest puts this
folder on the import path, which is what makes `from helpers import ...` work.
"""


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


def add_payment(connection, payment_id, amount_cents, note=""):
    connection.execute(
        "INSERT INTO payments VALUES (?, ?, ?, ?)",
        (payment_id, "2026-09-01", amount_cents, note)
    )
