"""Tests for the web pages.

The pages are served by the same application as the API, so these use the same
client fixture from conftest.py, against the same in-memory database. A page is
read with table_rows, which parses the HTML and returns what each cell says,
rather than by searching the page for a string.

Three kinds of test live here. What a page shows. That it shows the same figure
the API serves, which is the second of the three rules in web.py and the only
one a test can enforce directly. And that text from the database cannot become
markup in the browser.
"""

import os

import psells
import web

from helpers import add_product, add_return, add_sale, table_rows


# Column positions in the inventory table, so a test says which figure it
# means rather than which number it is.
ID, NAME, CATEGORY, CONDITION, AVAILABLE, LISTED, PARTNER_CUT, RETAIL = range(8)


# The inventory page ----------------------------------------------------------

def test_the_inventory_page_is_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_an_empty_inventory_says_so(client):
    """The {% else %} branch of the loop, which runs only when nothing did."""
    assert table_rows(client.get("/").text) == [["No products yet."]]


def test_a_product_is_one_row_with_every_column(client, db):
    """40 percent of a 100.00 retail price, from the partner_rate fixture."""
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    rows = table_rows(client.get("/").text)

    assert rows == [[
        "1", "Jordan 1 Chicago", "Shoes", "Brand New",
        "10", "$90.00", "$40.00", "",
    ]]


def test_available_counts_down_from_sales_and_returns(client, db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)
    add_return(db, 1, item_id=1, quantity=1)

    row = table_rows(client.get("/").text)[0]

    assert row[AVAILABLE] == "6"


def test_a_sold_out_product_is_still_listed(client, db):
    add_product(db, 1, quantity_received=2)
    add_sale(db, 1, item_id=1, quantity=2)

    row = table_rows(client.get("/").text)[0]

    assert row[AVAILABLE] == "0"


def test_a_discontinued_product_says_so_and_shows_its_fixed_cut(client, db):
    add_product(db, 1, quantity_received=1,
                retail_price_cents=0, retail_discontinued=1,
                partner_share_mode="custom_amount",
                partner_share_amount_cents=2500)

    row = table_rows(client.get("/").text)[0]

    assert row[RETAIL] == "Discontinued"
    assert row[PARTNER_CUT] == "$25.00"


def test_products_are_listed_in_id_order(client, db):
    add_product(db, 3, quantity_received=1)
    add_product(db, 1, quantity_received=1)
    add_product(db, 2, quantity_received=1)

    ids = [row[ID] for row in table_rows(client.get("/").text)]

    assert ids == ["1", "2", "3"]


# The page and the API agree --------------------------------------------------

def test_the_page_shows_the_figures_the_api_serves(client, db):
    """Every product, one of each partner share mode, and a cut that rounds.

    The API is the published record of these figures and has its own tests
    tying it to psells. This ties the page to the API, so the page cannot drift
    from psells without one of the two failing. The API's cents go through
    format_cents here only to compare like with like.
    """
    add_product(db, 1, quantity_received=10)
    add_product(db, 2, quantity_received=5,
                retail_price_cents=10003,
                partner_share_mode="custom_percent",
                partner_share_percent=12.5)
    add_product(db, 3, quantity_received=4,
                partner_share_mode="custom_amount",
                partner_share_amount_cents=1234)
    add_product(db, 4, quantity_received=1,
                retail_price_cents=0, retail_discontinued=1,
                partner_share_mode="custom_amount",
                partner_share_amount_cents=700)
    add_sale(db, 1, item_id=1, quantity=4)
    add_return(db, 1, item_id=3, quantity=1)

    served = {p["id"]: p for p in client.get("/products").json()}
    shown = {int(row[ID]): row for row in table_rows(client.get("/").text)}

    assert shown.keys() == served.keys()

    for product_id, product in served.items():
        row = shown[product_id]

        assert row[NAME] == product["name"]
        assert row[AVAILABLE] == str(product["quantity_available"])
        assert row[LISTED] == psells.format_cents(product["listed_price_cents"])
        assert row[PARTNER_CUT] == psells.format_cents(
            product["partner_share_cents"]
        )
        assert (row[RETAIL] == "Discontinued") == product["retail_discontinued"]


# Text from the database stays text -------------------------------------------

def test_markup_in_a_product_name_is_escaped(client, db):
    """A name that is a script must be shown as a name, never run.

    Autoescaping is what does this, and it is switched on by the template's
    file extension. This fails if a template is renamed away from .html, or if
    |safe is ever put on a field from the database.
    """
    name = '<script>alert("x")</script>'
    add_product(db, 1, quantity_received=1, name=name)

    page = client.get("/").text

    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert table_rows(page)[0][NAME] == name


def test_a_less_than_sign_in_a_name_is_shown_as_typed(client, db):
    """The everyday case of the same thing: a size note, not an attack."""
    add_product(db, 1, quantity_received=1, name="Slides, size <10 only")

    assert table_rows(client.get("/").text)[0][NAME] == "Slides, size <10 only"


# Where the templates live, and what the API documents ------------------------

def test_the_templates_sit_beside_web_py_not_beside_the_shell(client, db,
                                                              tmp_path,
                                                              monkeypatch):
    """Started from any other directory, the page still renders."""
    add_product(db, 1, quantity_received=1)
    monkeypatch.chdir(tmp_path)

    assert client.get("/").status_code == 200
    assert web.templates.env.loader.searchpath == [
        os.path.join(os.path.dirname(os.path.abspath(web.__file__)),
                     "templates")
    ]


def test_pages_are_not_in_the_api_documentation(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/" not in paths
    assert set(paths) == {"/products", "/dashboard", "/sales"}
