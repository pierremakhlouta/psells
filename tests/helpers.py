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


class _Figures(HTMLParser):
    """Collects each <dt> label and the <dd> value that follows it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.figures = {}
        self._tag = None
        self._text = []
        self._label = None

    def handle_starttag(self, tag, attrs):
        if tag in ("dt", "dd"):
            self._tag = tag
            self._text = []

    def handle_endtag(self, tag):
        if tag != self._tag:
            return

        text = " ".join("".join(self._text).split())

        if tag == "dt":
            self._label = text
        else:
            self.figures[self._label] = text

        self._tag = None

    def handle_data(self, data):
        if self._tag is not None:
            self._text.append(data)


def figures(html):
    """Every labelled figure in a page, as {label: value}, both as shown."""
    parser = _Figures()
    parser.feed(html)
    parser.close()

    return parser.figures


class _Forms(HTMLParser):
    """Collects every <form>, with each <input> and <select> inside it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self._form = None
        self._select = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if tag == "form":
            self._form = {
                "action": attributes.get("action", ""),
                "method": attributes.get("method", "get").lower(),
                "inputs": [],
            }
        elif self._form is None:
            return
        elif tag == "input":
            self._form["inputs"].append(attributes)
        elif tag == "select":
            self._select = dict(attributes, options=[], selected=None)
        elif tag == "option" and self._select is not None:
            self._select["options"].append(attributes.get("value"))

            if "selected" in attributes:
                self._select["selected"] = attributes.get("value")

    def handle_endtag(self, tag):
        if tag == "select" and self._select is not None:
            # A browser sends the selected option, or the first if none is.
            options = self._select["options"]
            chosen = self._select.pop("selected")
            self._select["value"] = chosen if chosen is not None else (
                options[0] if options else None)
            self._form["inputs"].append(self._select)
            self._select = None
        elif tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None


def forms(html):
    """Every form in a page: its action, its method, and its inputs.

    Each input is the full dictionary of its attributes, exactly as a browser
    would read them, so a test can see which name a form will send, what value
    it holds, and whether anything unexpected has been added to it. A <select>
    is listed among the inputs with its options, and value set to the option a
    browser would send: the selected one, or the first.
    """
    parser = _Forms()
    parser.feed(html)
    parser.close()

    return parser.forms


def form_data(form):
    """What a browser would send for this form as it stands, by name.

    A checkbox is sent only when ticked, and sends its value.
    """
    data = {}

    for field in form["inputs"]:
        if "name" not in field:
            continue

        if field.get("type") == "checkbox":
            if "checked" in field:
                data[field["name"]] = field.get("value", "on")
        else:
            data[field["name"]] = field.get("value") or ""

    return data
