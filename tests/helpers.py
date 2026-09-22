"""Row builders, and a table reader, shared by the test files.

These live here rather than in conftest.py because they are ordinary functions
rather than fixtures, so a test file imports them by name. pytest puts this
folder on the import path, which is what makes `from helpers import ...` work.
"""

from html.parser import HTMLParser


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


class _TableBody(HTMLParser):
    """Collects the text of every cell in the body of an HTML table."""

    def __init__(self):
        # convert_charrefs turns &lt; back into <, so a cell reads exactly as a
        # person sees it in the browser rather than as it was sent.
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._in_body = False
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self._in_body = True
        elif tag == "tr" and self._in_body:
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "tbody":
            self._in_body = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def table_rows(html):
    """The body rows of the table in a page, each a list of cell texts.

    Built on the standard library's HTML parser rather than on searching the
    page for a string, because "$40.00" appearing somewhere in a page is not
    the same as it appearing in the right column of the right row. Whitespace
    inside a cell is collapsed, so indentation in a template does not matter.
    """
    parser = _TableBody()
    parser.feed(html)
    parser.close()

    return parser.rows
