"""Tests for the web pages.

The pages are served by the same application as the API, so these use the same
client fixture from conftest.py, against the same in-memory database. A page is
read with table_rows, which parses the HTML and returns what each cell says,
rather than by searching the page for a string.

Three kinds of test live here. What a page shows. That it shows the same figures
the API serves, for the products and for the dashboard, which is the second of
the three rules in web.py and the only one a test can enforce directly. And that text from the database cannot become
markup in the browser.
"""

import os
from datetime import date

import pytest
from jinja2 import nodes

import psells
import web

from helpers import (add_payment, add_product, add_return, add_sale,
                     field_names, figures, form_data, forms, paragraphs,
                     table_rows)


# Column positions in the inventory table, so a test says which figure it
# means rather than which number it is.
ID, NAME, CATEGORY, CONDITION, AVAILABLE, LISTED, PARTNER_CUT, RETAIL, ACTIONS = (
    range(9))


# The inventory page ----------------------------------------------------------

def test_the_inventory_page_is_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_an_empty_inventory_says_so(client):
    """The {% else %} branch of the loop, which runs only when nothing did."""
    assert table_rows(client.get("/").text) == [["No products in stock."]]


def test_a_product_is_one_row_with_every_column(client, db):
    """40 percent of a 100.00 retail price, from the partner_rate fixture."""
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    rows = table_rows(client.get("/").text)

    assert rows == [[
        "1", "Jordan 1 Chicago", "Shoes", "Brand New",
        "10", "$90.00", "$40.00", "", "Sell Return Edit",
    ]]


def test_available_counts_down_from_sales_and_returns(client, db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)
    add_return(db, 1, item_id=1, quantity=1)

    row = table_rows(client.get("/").text)[0]

    assert row[AVAILABLE] == "6"


def test_a_sold_out_product_leaves_the_inventory_for_the_out_of_stock_page(
        client, db):
    add_product(db, 1, quantity_received=2)
    add_sale(db, 1, item_id=1, quantity=2)

    assert table_rows(client.get("/").text) == [["No products in stock."]]
    assert [row[ID] for row in table_rows(client.get("/out-of-stock").text)] == [
        "1"]


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


# Search ----------------------------------------------------------------------

def add_catalogue(db):
    """Five products across three categories, chosen so that a name search and
    a category search give different answers."""
    add_product(db, 1, quantity_received=1, name="Jordan 1 Chicago")
    add_product(db, 2, quantity_received=1, name="Jordan 4 Bred")
    add_product(db, 3, quantity_received=1, name="Box Logo Hoodie",
                category="Hoodies")
    add_product(db, 4, quantity_received=1, name="Air Max 90")
    add_product(db, 5, quantity_received=1, name="Chicago Bulls Cap",
                category="Hats")


def ids_shown(client, **params):
    """The ids of the product rows on the page, in the order shown.

    A product row has a cell for every column. The one-cell row that says
    nothing matched is not a product, so a search with no match gives [].
    """
    rows = table_rows(client.get("/", params=params).text)

    return [row[ID] for row in rows if len(row) == ACTIONS + 1]


def search_box(page):
    """The one input of the page's GET form."""
    (form,) = [form for form in forms(page) if form["method"] == "get"]
    (box,) = form["inputs"]

    return form, box


def test_a_search_narrows_the_table_by_name(client, db):
    add_catalogue(db)

    assert ids_shown(client, q="chicago") == ["1", "5"]


def test_a_search_matches_a_category(client, db):
    add_catalogue(db)

    assert ids_shown(client, q="hoodies") == ["3"]


def test_a_search_ignores_case(client, db):
    add_catalogue(db)

    assert ids_shown(client, q="SHOES") == ["1", "2", "4"]


def test_the_page_searches_with_the_command_lines_search(client, db):
    """Same function, so the same answer, for every term tried."""
    add_catalogue(db)
    everything = psells.all_products(db)

    for term in ["jordan", "o", "CHICAGO", "hats", "zzz"]:
        expected = [
            str(product["id"])
            for product in psells.find_items_by_name_or_category(everything,
                                                                 term)
        ]

        assert ids_shown(client, q=term) == expected, term


def test_no_search_term_shows_everything(client, db):
    add_catalogue(db)

    assert ids_shown(client) == ["1", "2", "3", "4", "5"]
    assert ids_shown(client, q="") == ["1", "2", "3", "4", "5"]
    assert ids_shown(client, q="   ") == ["1", "2", "3", "4", "5"]


def test_spaces_around_a_term_are_ignored(client, db):
    """The command line strips what it reads, and so does the page."""
    add_catalogue(db)

    assert ids_shown(client, q="  bred ") == ["2"]


def test_a_search_with_no_match_says_so(client, db):
    add_catalogue(db)

    rows = table_rows(client.get("/", params={"q": "zzz"}).text)

    assert rows == [['No products in stock match "zzz".']]


def test_the_search_goes_through_the_form_the_page_serves(client, db):
    """Read the form's own action and field name, then submit through them.

    A test that built ?q= by hand would pass with the input misnamed, and the
    real search box would do nothing.
    """
    add_catalogue(db)

    form, box = search_box(client.get("/").text)
    response = client.get(form["action"], params={box["name"]: "chicago"})

    assert box["type"] == "search"
    assert [row[ID] for row in table_rows(response.text)] == ["1", "5"]


def test_the_term_is_put_back_in_the_box(client, db):
    add_catalogue(db)

    _, box = search_box(client.get("/", params={"q": " bred "}).text)

    assert box["value"] == "bred"


def test_a_quote_in_the_search_stays_inside_the_value(client, db):
    """Unescaped, the quote would close value early and add an attribute."""
    term = '" autofocus onfocus="alert(1)'

    page = client.get("/", params={"q": term}).text
    _, box = search_box(page)

    assert box["value"] == term
    assert "onfocus" not in box
    assert 'onfocus="alert(1)"' not in page


def test_a_search_does_not_change_the_dashboard(client, db):
    """The panel describes the business, not the rows that happen to show."""
    add_catalogue(db)
    add_sale(db, 1, item_id=3, quantity=1)

    everything = figures(client.get("/").text)
    searched = figures(client.get("/", params={"q": "chicago"}).text)

    assert searched == everything


# The out-of-stock page -------------------------------------------------------

# Column positions in the out-of-stock table: the inventory's, with the reason
# after Available.
(OUT_ID, OUT_NAME, OUT_CATEGORY, OUT_CONDITION, OUT_AVAILABLE, OUT_REASON,
 OUT_LISTED, OUT_PARTNER_CUT, OUT_RETAIL, OUT_ACTIONS) = range(10)


def out_of_stock_rows(client, **params):
    return table_rows(client.get("/out-of-stock", params=params).text)


def add_both_kinds(db):
    """Two products in stock and three out, one for each reason, with
    "Chicago" in the name of one of each kind."""
    add_product(db, 1, quantity_received=3, name="Jordan 1 Chicago")
    add_product(db, 2, quantity_received=2, name="Air Max 90")
    add_product(db, 3, quantity_received=2, name="Chicago Bulls Cap",
                category="Hats")
    add_product(db, 4, quantity_received=1, name="Box Logo Hoodie",
                category="Hoodies")
    add_product(db, 5, quantity_received=3, name="Jordan 4 Bred")
    add_sale(db, 1, item_id=1, quantity=1)
    add_sale(db, 2, item_id=3, quantity=2)
    add_return(db, 1, item_id=4, quantity=1)
    add_sale(db, 3, item_id=5, quantity=2)
    add_return(db, 2, item_id=5, quantity=1)


def test_the_out_of_stock_page_is_html(client):
    response = client.get("/out-of-stock")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_with_nothing_out_of_stock_the_page_says_so_and_has_no_table(client,
                                                                     db):
    add_product(db, 1, quantity_received=1)
    page = client.get("/out-of-stock").text

    assert "<table" not in page
    assert paragraphs(page, "empty") == [("No products are out of stock.", [])]


def test_every_product_is_on_exactly_one_of_the_two_pages(client, db):
    add_both_kinds(db)

    inventory = [row[ID] for row in table_rows(client.get("/").text)]
    out = [row[OUT_ID] for row in out_of_stock_rows(client)]

    assert inventory == ["1", "2"]
    assert out == ["3", "4", "5"]
    assert sorted(inventory + out) == sorted(
        str(p["id"]) for p in client.get("/products").json())


def test_each_out_of_stock_row_gives_the_reason_psells_gives(client, db):
    add_both_kinds(db)

    reasons = {row[OUT_ID]: row[OUT_REASON] for row in out_of_stock_rows(client)}

    assert reasons == {"3": "Sold out", "4": "Returned",
                       "5": "2 sold, 1 returned of 3"}
    for product in psells.out_of_stock_products(db):
        assert reasons[str(product["id"])] == psells.out_of_stock_reason(
            product)


def test_the_out_of_stock_page_shows_what_the_api_serves(client, db):
    add_both_kinds(db)
    add_product(db, 6, quantity_received=1, name="Odd cut",
                retail_price_cents=10003, partner_share_mode="custom_percent",
                partner_share_percent=12.5)
    add_sale(db, 4, item_id=6, quantity=1)

    rows = out_of_stock_rows(client)

    assert rows == [
        [str(p["id"]), p["name"], p["category"], p["condition"],
         str(p["quantity_available"]), p["reason"],
         psells.format_cents(p["listed_price_cents"]),
         psells.format_cents(p["partner_share_cents"]),
         "Discontinued" if p["retail_discontinued"] else "", "Edit"]
        for p in client.get("/products/out-of-stock").json()
    ]


def test_each_page_searches_only_its_own_products(client, db):
    add_both_kinds(db)

    assert ids_shown(client, q="chicago") == ["1"]
    assert [row[OUT_ID] for row in out_of_stock_rows(client, q="chicago")] == [
        "3"]
    assert [row[OUT_ID] for row in out_of_stock_rows(client, q=" HOODIES ")] == [
        "4"]


def test_the_out_of_stock_page_searches_with_the_command_lines_search(client,
                                                                      db):
    add_both_kinds(db)
    out = psells.out_of_stock_products(db)

    for term in ["jordan", "o", "CHICAGO", "hats", "zzz"]:
        expected = [str(product["id"]) for product in
                    psells.find_items_by_name_or_category(out, term)]
        shown = [row[OUT_ID] for row in out_of_stock_rows(client, q=term)]

        assert shown == expected, term


def test_an_out_of_stock_search_with_no_match_says_so(client, db):
    add_both_kinds(db)
    page = client.get("/out-of-stock", params={"q": "air max"}).text

    assert "<table" not in page
    assert paragraphs(page, "empty") == [
        ('No out-of-stock products match "air max".', [])]


def test_the_out_of_stock_search_goes_through_its_own_form(client, db):
    add_both_kinds(db)

    form, box = search_box(client.get("/out-of-stock").text)
    response = client.get(form["action"], params={box["name"]: "bred"})

    assert form["action"].endswith("/out-of-stock")
    assert [row[OUT_ID] for row in table_rows(response.text)] == ["5"]


def test_out_of_stock_rows_offer_edit_and_the_edit_page_offers_delete(client,
                                                                      db):
    add_both_kinds(db)
    page = client.get("/out-of-stock").text

    assert {row[OUT_ACTIONS] for row in table_rows(page)} == {"Edit"}
    assert "/delete" not in page
    assert "/products/4/delete" in client.get("/products/4/edit").text


def test_markup_in_a_name_is_escaped_on_the_out_of_stock_page(client, db):
    name = '<script>alert("x")</script>'
    add_product(db, 1, quantity_received=1, name=name)
    add_sale(db, 1, item_id=1, quantity=1)

    page = client.get("/out-of-stock").text

    assert "<script>" not in page
    assert out_of_stock_rows(client)[0][OUT_NAME] == name


def test_every_page_links_to_the_out_of_stock_page_from_the_nav(client, db):
    add_product(db, 1, quantity_received=1)

    for path in ["/", "/out-of-stock", "/products/new", "/products/1/edit",
                 "/payments/new"]:
        page = client.get(path).text
        assert 'href="http://testserver/out-of-stock">Out of stock</a>' in page


def test_selling_the_last_unit_is_confirmed_with_a_link_to_out_of_stock(
        client, db):
    add_product(db, 1, quantity_received=2, name="Jordan 1 Chicago")

    response = submit_sale_form(client, quantity="2", sale_price="90.00",
                                follow_redirects=True)
    notices = paragraphs(response.text, "notice")

    assert notices == [
        ("Recorded a sale of Jordan 1 Chicago, id 1.", []),
        ("Jordan 1 Chicago has no units available, so it is listed under "
         "Out of stock.", ["http://testserver/out-of-stock"]),
    ]
    assert table_rows(response.text) == [["No products in stock."]]


def test_a_sale_that_leaves_stock_has_no_out_of_stock_notice(client, db):
    add_product(db, 1, quantity_received=2, name="Jordan 1 Chicago")

    response = submit_sale_form(client, quantity="1", sale_price="90.00",
                                follow_redirects=True)

    assert paragraphs(response.text, "notice") == [
        ("Recorded a sale of Jordan 1 Chicago, id 1.", [])]


def test_returning_the_last_unit_is_confirmed_with_the_same_link(client, db):
    add_product(db, 1, quantity_received=1, name="Box Logo Hoodie")

    response = submit_return_form(client, quantity="1", follow_redirects=True)
    (_, (_, links)) = paragraphs(response.text, "notice")

    assert links == ["http://testserver/out-of-stock"]


def test_an_edit_from_the_out_of_stock_page_is_confirmed(client, db):
    add_product(db, 1, quantity_received=1, name="Sold Hoodie")
    add_sale(db, 1, item_id=1, quantity=1)

    response = submit_edit_form(client, notes="Kept the box",
                                follow_redirects=True)
    texts = [text for text, _ in paragraphs(response.text, "notice")]

    assert texts == [
        "Saved changes to Sold Hoodie, id 1.",
        "Sold Hoodie has no units available, so it is listed under "
        "Out of stock.",
    ]


# The history pages -----------------------------------------------------------

HISTORY_PAGES = {
    "/sales-history": "No sales recorded yet.",
    "/returns-history": "No returns recorded yet.",
    "/payments-history": "No payments recorded yet.",
}


def add_history(db):
    """Sales, returns and payments entered out of date order, with two of
    each on one date, so the order shown is the page's own."""
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")
    add_product(db, 2, quantity_received=5, name="Box Logo Hoodie",
                category="Hoodies")
    add_sale(db, 1, item_id=1, quantity=1, sale_price_cents=9000,
             partner_share_cents=3500, date="2026-09-03")
    add_sale(db, 2, item_id=2, quantity=3, sale_price_cents=12550,
             partner_share_cents=4020, date="2026-09-10")
    add_sale(db, 3, item_id=1, quantity=2, sale_price_cents=8800,
             partner_share_cents=3333, date="2026-09-03")
    add_return(db, 1, item_id=2, quantity=1, date="2026-09-12",
               notes="Torn seam")
    add_return(db, 2, item_id=1, quantity=1, date="2026-09-05",
               notes="Wrong size")
    add_return(db, 3, item_id=1, quantity=2, date="2026-09-12")
    add_payment(db, 1, 5000, "First transfer", date="2026-09-15")
    add_payment(db, 2, 12345, "", date="2026-09-20")
    add_payment(db, 3, 0, "Nothing owed", date="2026-09-15")


@pytest.mark.parametrize("path", HISTORY_PAGES)
def test_an_empty_history_page_says_so_and_has_no_table(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<table" not in response.text
    assert paragraphs(response.text, "empty") == [(HISTORY_PAGES[path], [])]


@pytest.mark.parametrize("path", HISTORY_PAGES)
def test_every_page_links_to_the_history_pages_from_the_nav(client, db, path):
    add_product(db, 1, quantity_received=1)
    label = {"/sales-history": "Sales", "/returns-history": "Returns",
             "/payments-history": "Payments"}[path]

    for page in ["/", "/out-of-stock", *HISTORY_PAGES, "/products/new",
                 "/products/1/edit", "/payments/new"]:
        assert f'href="http://testserver{path}">{label}</a>' in client.get(
            page).text, page


def test_the_sales_page_shows_sales_history_newest_first(client, db):
    add_history(db)

    rows = table_rows(client.get("/sales-history").text)

    assert rows == [
        ["2026-09-10", "Box Logo Hoodie", "Hoodies", "3",
         "$125.50", "$376.50", "$120.60", "$255.90", "Edit Delete"],
        ["2026-09-03", "Jordan 1 Chicago", "Shoes", "2",
         "$88.00", "$176.00", "$66.66", "$109.34", "Edit Delete"],
        ["2026-09-03", "Jordan 1 Chicago", "Shoes", "1",
         "$90.00", "$90.00", "$35.00", "$55.00", "Edit Delete"],
    ]


def test_the_sales_page_shows_what_sales_history_returns(client, db):
    add_history(db)

    rows = table_rows(client.get("/sales-history").text)

    assert rows == [
        [str(sale["date"]), sale["name"], sale["category"],
         str(sale["quantity"]), psells.format_cents(sale["sale_price_cents"]),
         psells.format_cents(sale["sale_total_cents"]),
         psells.format_cents(sale["partner_cut_cents"]),
         psells.format_cents(sale["profit_cents"]), "Edit Delete"]
        for sale in psells.sales_history(db)
    ]


def test_editing_a_product_never_changes_its_row_in_the_sales_page(client,
                                                                   db):
    add_history(db)
    before = table_rows(client.get("/sales-history").text)

    submit_edit_form(client, listed_price="10.00", retail_price="20.00",
                     partner_share_mode="custom_percent",
                     partner_share_percent="90")
    after = table_rows(client.get("/sales-history").text)

    assert stored(db)["listed_price_cents"] == 1000
    assert after == before


def test_the_returns_page_shows_returns_newest_first_with_notes(client, db):
    add_history(db)

    rows = table_rows(client.get("/returns-history").text)

    assert rows == [
        ["2026-09-12", "Jordan 1 Chicago", "Shoes", "2", "", "Edit Delete"],
        ["2026-09-12", "Box Logo Hoodie", "Hoodies", "1", "Torn seam", "Edit Delete"],
        ["2026-09-05", "Jordan 1 Chicago", "Shoes", "1", "Wrong size", "Edit Delete"],
    ]


def test_the_payments_page_shows_payments_newest_first(client, db):
    add_history(db)

    rows = table_rows(client.get("/payments-history").text)

    assert rows == [
        ["2026-09-20", "$123.45", "", "Edit Delete"],
        ["2026-09-15", "$0.00", "Nothing owed", "Edit Delete"],
        ["2026-09-15", "$50.00", "First transfer", "Edit Delete"],
    ]


def test_the_history_pages_show_what_the_api_serves(client, db):
    add_history(db)
    money = psells.format_cents

    assert table_rows(client.get("/sales-history").text) == [
        [s["date"], s["name"], s["category"], str(s["quantity"]),
         money(s["sale_price_cents"]), money(s["sale_total_cents"]),
         money(s["partner_cut_cents"]), money(s["profit_cents"]),
         "Edit Delete"]
        for s in client.get("/sales").json()
    ]
    assert table_rows(client.get("/returns-history").text) == [
        [r["date"], r["name"], r["category"], str(r["quantity"]), r["notes"],
         "Edit Delete"]
        for r in client.get("/returns").json()
    ]
    assert table_rows(client.get("/payments-history").text) == [
        [p["date"], money(p["amount_cents"]), p["notes"], "Edit Delete"]
        for p in client.get("/payments").json()
    ]


def test_a_payment_recorded_on_the_page_appears_in_the_history(client, db):
    form = payment_form_of(client)
    data = form_data(form)
    data.update(amount="75.25", date="2026-09-30", notes="Cash")
    client.post(form["action"], data=data)

    rows = table_rows(client.get("/payments-history").text)

    assert rows == [["2026-09-30", "$75.25", "Cash", "Edit Delete"]]


def test_markup_in_history_text_is_escaped(client, db):
    name = '<script>alert("x")</script>'
    add_product(db, 1, quantity_received=5, name=name)
    add_sale(db, 1, item_id=1, quantity=1)
    add_return(db, 1, item_id=1, quantity=1, notes=name)
    add_payment(db, 1, 100, name)

    for path, column in [("/sales-history", 1), ("/returns-history", 1),
                         ("/returns-history", 4), ("/payments-history", 2)]:
        page = client.get(path).text

        assert "<script>" not in page, path
        assert table_rows(page)[0][column] == name, path


# Correcting a sale, return or payment ---------------------------------------------

def posting_form(page):
    (form,) = [form for form in forms(page) if form["method"] == "post"]
    return form


def submit_served_form(client, path, **typed):
    """Open a page, fill in its one posting form as served, and submit it."""
    form = posting_form(client.get(path).text)
    data = form_data(form)
    data.update(typed)
    return client.post(form["action"], data=data, follow_redirects=False)


def corrections(db):
    return db.execute("SELECT record_type, record_id, action FROM corrections "
                      "ORDER BY id").fetchall()


def test_every_history_row_links_to_its_edit_and_delete_pages(client, db):
    add_history(db)

    for path, kind in [("/sales-history", "sales"),
                       ("/returns-history", "returns"),
                       ("/payments-history", "payments")]:
        page = client.get(path).text
        for record_id in (1, 2, 3):
            assert f'href="http://testserver/{kind}-history/{record_id}/edit"' in page
            assert f'href="http://testserver/{kind}-history/{record_id}/delete"' in page


def test_a_sale_edit_form_starts_from_the_sale_and_shows_what_stays(client,
                                                                    db):
    add_history(db)

    page = client.get("/sales-history/3/edit").text
    form = posting_form(page)

    assert form["action"].endswith("/sales-history/3/edit")
    assert form_data(form) == {"quantity": "2", "sale_price": "88.00",
                               "date": "2026-09-03"}
    assert figures(page)["Product"] == "Jordan 1 Chicago, id 1"
    assert figures(page)["Partner cut per unit, frozen"] == "$33.33"
    assert figures(page)["Available now"] == str(
        web.find_product(db, 1)["quantity_available"])


def test_editing_a_sale_from_its_form_saves_logs_and_says_so(client, db):
    add_history(db)

    response = submit_served_form(client, "/sales-history/3/edit",
                                  quantity="1", sale_price="80.00")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/sales-history?edited=3")
    page = client.get(response.headers["location"]).text
    assert paragraphs(page, "notice") == [
        ("Saved changes to the sale of Jordan 1 Chicago dated 2026-09-03.", [])]
    edited = psells.find_sale(db, 3)
    assert (edited["quantity"], edited["sale_price_cents"],
            edited["partner_share_cents"]) == (1, 8000, 3333)
    assert corrections(db) == [{"record_type": "sale", "record_id": 3,
                                "action": "edit"}]


def test_a_sale_edit_with_wrong_text_is_shown_again_and_changes_nothing(
        client, db):
    add_history(db)

    response = submit_served_form(client, "/sales-history/3/edit",
                                  quantity="two", sale_price="-1")

    assert response.status_code == 422
    assert "Nothing was changed." in response.text
    assert posting_form(response.text)["inputs"][1]["value"] == "two"
    assert psells.find_sale(db, 3)["quantity"] == 2
    assert corrections(db) == []


def test_a_sale_edit_past_the_stock_is_a_409_with_the_reason(client, db):
    add_history(db)
    most = web.find_product(db, 1)["quantity_available"] + 2

    response = submit_served_form(client, "/sales-history/3/edit",
                                  quantity=str(most + 1))

    assert response.status_code == 409
    assert f"can be at most {most}, not {most + 1}." in response.text
    assert corrections(db) == []


def test_the_delete_page_says_what_deleting_a_sale_changes(client, db):
    add_history(db)

    page = client.get("/sales-history/2/delete").text

    assert paragraphs(page, "lead") == [(
        "Deleting it gives its 3 sold back to Box Logo Hoodie's stock, and "
        "lowers revenue by $376.50, the partner share earned by $120.60 and "
        "profit by $255.90. The sale as it was is kept in the corrections "
        "log.", [])]
    assert psells.find_sale(db, 2) is not None


def test_deleting_a_sale_from_its_confirmation(client, db):
    add_history(db)
    before = psells.dashboard_totals(db)

    response = submit_served_form(client, "/sales-history/2/delete")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/sales-history?deleted=2")
    page = client.get(response.headers["location"]).text
    assert paragraphs(page, "notice") == [
        ("Deleted the sale dated 2026-09-10. It is kept in the corrections "
         "log.", [])]
    assert psells.find_sale(db, 2) is None
    after = psells.dashboard_totals(db)
    assert before["total_revenue"] - after["total_revenue"] == 37650
    assert corrections(db) == [{"record_type": "sale", "record_id": 2,
                                "action": "delete"}]


def test_a_notice_names_only_a_record_the_log_or_the_list_has(client, db):
    """deleted=3 names a sale that was edited, not deleted: the log has a row
    for it, but not a delete."""
    add_history(db)
    psells.update_sale(db, 3, 1, 8800, "2026-09-03")

    for query in ["?deleted=2", "?deleted=3", "?deleted=99", "?deleted=abc",
                  "?edited=99", "?edited=abc"]:
        page = client.get("/sales-history" + query).text
        assert paragraphs(page, "notice") == [], query


def test_editing_and_deleting_a_return_from_its_pages(client, db):
    add_history(db)

    edited = submit_served_form(client, "/returns-history/1/edit",
                                quantity="2", notes="Both torn")
    deleted = submit_served_form(client, "/returns-history/2/delete")

    assert edited.headers["location"].endswith("/returns-history?edited=1")
    assert deleted.headers["location"].endswith("/returns-history?deleted=2")
    assert (psells.find_return(db, 1)["quantity"],
            psells.find_return(db, 1)["notes"]) == (2, "Both torn")
    assert psells.find_return(db, 2) is None
    assert [c["action"] for c in corrections(db)] == ["edit", "delete"]


def test_editing_and_deleting_a_payment_from_its_pages(client, db):
    add_history(db)

    edit_page = client.get("/payments-history/1/edit").text
    edited = submit_served_form(client, "/payments-history/1/edit",
                                amount="45.00")
    deleted = submit_served_form(client, "/payments-history/2/delete")

    assert form_data(posting_form(edit_page)) == {
        "amount": "50.00", "date": "2026-09-15", "notes": "First transfer"}
    assert edited.headers["location"].endswith("/payments-history?edited=1")
    assert deleted.headers["location"].endswith("/payments-history?deleted=2")
    assert psells.dashboard_totals(db)["total_paid"] == 4500
    assert paragraphs(client.get(deleted.headers["location"]).text,
                      "notice") == [
        ("Deleted the payment dated 2026-09-20. It is kept in the corrections "
         "log.", [])]


@pytest.mark.parametrize("kind", ["sales", "returns", "payments"])
@pytest.mark.parametrize("action", ["edit", "delete"])
def test_a_record_that_does_not_exist_is_a_404_page(client, db, kind, action):
    path = f"/{kind}-history/99/{action}"

    for response in (client.get(path), client.post(path)):
        assert response.status_code == 404
        assert "There is no" in response.text


def test_opening_a_delete_page_deletes_nothing(client, db):
    add_history(db)

    for kind in ("sales", "returns", "payments"):
        assert client.get(f"/{kind}-history/1/delete").status_code == 200

    assert corrections(db) == []
    assert psells.find_sale(db, 1) is not None


def test_markup_in_notes_is_escaped_on_the_correction_pages(client, db):
    name = '<script>alert("x")</script>'
    add_product(db, 1, quantity_received=5)
    add_return(db, 1, item_id=1, quantity=1, notes=name)

    for path in ["/returns-history/1/edit", "/returns-history/1/delete"]:
        assert "<script>" not in client.get(path).text, path


# Adding a product ------------------------------------------------------------

def add_form(client):
    """The form the add page serves, read the way a browser reads it."""
    (form,) = [form for form in forms(client.get("/products/new").text)
               if form["method"] == "post"]

    return form


def submit_add_form(client, follow_redirects=False, headers=None, **typed):
    """Fill in the served form and submit it through its own action.

    Starts from what the blank form would send, so a field the page forgot to
    offer is missing here too, then applies what the test types.
    """
    form = add_form(client)
    data = form_data(form)
    data.update(typed)

    return client.post(form["action"], data=data, headers=headers or {},
                       follow_redirects=follow_redirects)


GOOD = {
    "category": "Shoes",
    "name": "Jordan 1 Chicago",
    "quantity_received": "10",
    "retail_price": "100.00",
    "listed_price": "90.00",
    "condition": "Brand New",
}


def field(form, name):
    (found,) = [f for f in form["inputs"] if f.get("name") == name]

    return found


def products_stored(db):
    return db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]


def test_the_add_form_offers_every_field_the_reader_reads(client):
    """Three lists of the same names: the form, the model that receives it,
    and psells. A field missing from any one would be silently dropped."""
    form = add_form(client)
    offered = field_names(form)

    assert form["method"] == "post"
    assert form["action"].endswith("/products/new")
    assert offered == set(psells.PRODUCT_FORM_FIELDS)
    assert set(web.ProductForm.model_fields) == set(psells.PRODUCT_FORM_FIELDS)


def test_a_blank_form_starts_empty_on_the_default_share(client):
    data = form_data(add_form(client))

    assert data.pop("partner_share_mode") == "default"
    assert set(data.values()) == {""}


def test_adding_a_product_answers_303_to_the_inventory(client, db):
    """303, not 307: a 307 would make the browser post the form again."""
    response = submit_add_form(client, **GOOD)
    # The database's sequence chose the id, so read it rather than assume it.
    new_id = db.execute("SELECT id FROM products").fetchone()["id"]

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/?added={new_id}")
    assert products_stored(db) == 1


def test_the_product_is_stored_as_typed_and_in_cents(client, db):
    submit_add_form(client, **GOOD, notes="boxed")

    stored = dict(db.execute("SELECT * FROM products").fetchone())

    assert stored["name"] == "Jordan 1 Chicago"
    assert stored["quantity_received"] == 10
    assert stored["retail_price_cents"] == 10000
    assert stored["listed_price_cents"] == 9000
    assert stored["notes"] == "boxed"
    assert stored["partner_share_mode"] == "default"


def test_after_adding_the_inventory_shows_it_and_says_so(client, db):
    page = submit_add_form(client, follow_redirects=True, **GOOD).text
    new_id = db.execute("SELECT id FROM products").fetchone()["id"]

    assert [row[NAME] for row in table_rows(page)] == ["Jordan 1 Chicago"]
    assert f"Added Jordan 1 Chicago, id {new_id}." in page


@pytest.mark.parametrize("typed, expected", [
    ({"partner_share_mode": "custom_percent", "partner_share_percent": "35.5"},
     ("custom_percent", 35.5, None, 0)),
    ({"partner_share_mode": "custom_amount", "partner_share_amount": "12.50"},
     ("custom_amount", None, 1250, 0)),
    ({"retail_discontinued": "yes", "retail_price": "",
      "partner_share_mode": "custom_amount", "partner_share_amount": "7.00"},
     ("custom_amount", None, 700, 1)),
])
def test_each_partner_share_is_stored(client, db, typed, expected):
    response = submit_add_form(client, **{**GOOD, **typed})

    assert response.status_code == 303
    assert tuple(db.execute(
        "SELECT partner_share_mode, partner_share_percent, "
        "partner_share_amount_cents, retail_discontinued FROM products"
    ).fetchone().values()) == expected


def test_the_form_stores_what_create_product_would(client, db):
    """Same values by both routes, same row apart from the id."""
    submit_add_form(client, **GOOD, notes="boxed")
    psells.create_product(
        db, category="Shoes", name="Jordan 1 Chicago", quantity_received=10,
        retail_discontinued=False, retail_price_cents=10000,
        listed_price_cents=9000, condition="Brand New", notes="boxed",
        partner_share_mode="default", partner_share_percent=None,
        partner_share_amount_cents=None,
    )

    first, second = [dict(row) for row in db.execute(
        "SELECT * FROM products ORDER BY id")]
    first.pop("id")
    second.pop("id")

    assert first == second


def test_an_empty_form_is_refused_with_422_and_nothing_stored(client, db):
    response = submit_add_form(client)

    assert response.status_code == 422
    assert products_stored(db) == 0
    assert "The product was not added." in response.text


def test_a_refused_form_keeps_everything_typed(client, db):
    """One typo, and every other field, the box and the dropdown come back."""
    typed = {**GOOD, "listed_price": "9O.00", "notes": "boxed, <10 only",
             "retail_discontinued": "yes", "retail_price": "",
             "partner_share_mode": "custom_amount",
             "partner_share_amount": "12.50"}

    response = submit_add_form(client, **typed)
    form = forms(response.text)[-1]

    assert response.status_code == 422
    assert form_data(form) == {**typed, "partner_share_percent": ""}
    assert "checked" in field(form, "retail_discontinued")
    assert field(form, "partner_share_mode")["value"] == "custom_amount"
    assert field(form, "listed_price")["aria-invalid"] == "true"
    assert psells.MONEY_TEXT_PROBLEM in response.text


def test_markup_typed_into_the_form_stays_text_when_shown_again(client, db):
    response = submit_add_form(client, **{**GOOD, "listed_price": "abc",
                                          "name": '<script>alert("x")</script>'})

    assert response.status_code == 422
    assert "<script>" not in response.text
    assert field(forms(response.text)[-1], "name")["value"] == (
        '<script>alert("x")</script>')


def test_a_forged_mode_is_refused_as_bad_input_not_a_server_error(client, db):
    response = submit_add_form(client, **GOOD, partner_share_mode="everything")

    assert response.status_code == 422
    assert products_stored(db) == 0


def test_a_percentage_of_nan_is_refused(client, db):
    response = submit_add_form(client, **GOOD,
                               partner_share_mode="custom_percent",
                               partner_share_percent="nan")

    assert response.status_code == 422
    assert products_stored(db) == 0


def test_the_confirmation_names_only_a_product_that_exists(client, db):
    add_product(db, 1, quantity_received=1, name="Jordan 1 Chicago")

    for added in ["999", "abc", "", "1.0"]:
        page = client.get("/", params={"added": added})

        assert page.status_code == 200
        assert "Added " not in page.text, added

    assert "Added Jordan 1 Chicago, id 1." in client.get(
        "/", params={"added": "1"}).text


def test_an_add_from_another_site_is_refused(client, db):
    response = submit_add_form(client, **GOOD,
                               headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert products_stored(db) == 0


# Editing a product -----------------------------------------------------------

def edit_form(client, product_id=1):
    response = client.get(f"/products/{product_id}/edit")
    (form,) = [form for form in forms(response.text) if form["method"] == "post"]

    return form


def submit_edit_form(client, product_id=1, follow_redirects=False,
                     headers=None, **typed):
    """Submit the edit form as served, with what the test types on top."""
    form = edit_form(client, product_id)
    data = form_data(form)
    data.update(typed)

    return client.post(form["action"], data=data, headers=headers or {},
                       follow_redirects=follow_redirects)


def stored(db, product_id=1):
    return dict(db.execute("SELECT * FROM products WHERE id = %s",
                           (product_id,)).fetchone())


def test_every_row_links_to_its_edit_page(client, db):
    add_product(db, 7, quantity_received=1)

    page = client.get("/").text

    assert 'href="http://testserver/products/7/edit"' in page
    assert table_rows(page)[0][ACTIONS] == "Sell Return Edit"


def test_the_edit_form_opens_filled_with_the_product(client, db):
    add_product(db, 1, quantity_received=10, notes="boxed",
                partner_share_mode="custom_percent",
                partner_share_percent=33.333333)

    data = form_data(edit_form(client))

    assert data == {
        "category": "Shoes", "name": "Product 1", "condition": "Brand New",
        "quantity_received": "10", "retail_price": "100.00",
        "listed_price": "90.00", "partner_share_mode": "custom_percent",
        "partner_share_percent": "33.333333", "partner_share_amount": "",
        "notes": "boxed",
    }


@pytest.mark.parametrize("overrides", [
    {},
    {"partner_share_mode": "custom_percent", "partner_share_percent": 33.333333},
    {"partner_share_mode": "custom_amount", "partner_share_amount_cents": 1234},
    {"retail_discontinued": 1, "retail_price_cents": 0,
     "partner_share_mode": "custom_amount", "partner_share_amount_cents": 700},
    {"notes": ""},
])
def test_saving_the_form_untouched_changes_nothing(client, db, overrides):
    """What the form shows must read back as exactly what is stored,
    including a percentage no short form would survive."""
    add_product(db, 1, quantity_received=10, **overrides)
    before = stored(db)

    response = submit_edit_form(client)

    assert response.status_code == 303
    assert stored(db) == before


def test_an_edit_answers_303_and_says_so(client, db):
    add_product(db, 1, quantity_received=10)

    response = submit_edit_form(client, name="Renamed")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/?edited=1")
    assert "Saved changes to Renamed, id 1." in client.get(
        response.headers["location"]).text


def test_an_edit_stores_every_field_typed(client, db):
    add_product(db, 1, quantity_received=10)

    submit_edit_form(client, category="Hats", quantity_received="12",
                     retail_price="80.00", listed_price="75.50",
                     partner_share_mode="custom_amount",
                     partner_share_amount="20.00", notes="new")

    row = stored(db)

    assert (row["category"], row["quantity_received"],
            row["retail_price_cents"], row["listed_price_cents"],
            row["partner_share_mode"], row["partner_share_amount_cents"],
            row["notes"]) == ("Hats", 12, 8000, 7550, "custom_amount",
                              2000, "new")


def test_emptied_notes_are_cleared(client, db):
    """Decided: on a form that opens filled in, empty means cleared."""
    add_product(db, 1, quantity_received=10, notes="boxed")

    submit_edit_form(client, notes="")

    assert stored(db)["notes"] == ""


def test_an_emptied_name_is_refused_not_kept(client, db):
    add_product(db, 1, quantity_received=10, name="Keep me")

    response = submit_edit_form(client, name="")

    assert response.status_code == 422
    assert stored(db)["name"] == "Keep me"
    assert "Name cannot be blank." in response.text
    assert field(forms(response.text)[-1], "name")["value"] == ""


def test_the_intake_floor_is_enforced_from_the_page(client, db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=4)
    add_return(db, 1, item_id=1, quantity=1)

    response = submit_edit_form(client, quantity_received="4",
                                listed_price="abc")

    assert response.status_code == 422
    assert stored(db)["quantity_received"] == 10
    assert "cannot be less than 5" in response.text
    assert psells.MONEY_TEXT_PROBLEM in response.text


def test_a_refused_edit_keeps_what_was_typed(client, db):
    add_product(db, 1, quantity_received=10)

    response = submit_edit_form(client, name="New name", listed_price="9O",
                                partner_share_mode="custom_amount",
                                partner_share_amount="5.00")
    data = form_data(forms(response.text)[-1])

    assert response.status_code == 422
    assert (data["name"], data["listed_price"], data["partner_share_mode"],
            data["partner_share_amount"]) == ("New name", "9O",
                                              "custom_amount", "5.00")


def test_an_edit_never_rewrites_a_sale_from_the_page(client, db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=2, sale_price_cents=9000,
             partner_share_cents=3500)
    before = figures(client.get("/").text)

    submit_edit_form(client, partner_share_mode="custom_amount",
                     partner_share_amount="1.00")

    assert db.execute("SELECT partner_share_cents FROM sales").fetchone()["partner_share_cents"] == 3500
    assert figures(client.get("/").text) == before


def test_editing_a_product_that_does_not_exist_is_a_404_page(client, db):
    for method in ("get", "post"):
        response = getattr(client, method)("/products/99/edit")

        assert response.status_code == 404
        assert "No product 99" in response.text


def test_an_id_that_is_not_a_number_does_not_match_the_route(client):
    """{product_id:int} in the path: "abc" matches no route and is a 404.
    Written as {product_id}, it would match and fail validation with a 422."""
    for method in ("get", "post"):
        assert getattr(client, method)("/products/abc/edit").status_code == 404


def test_an_edit_from_another_site_is_refused(client, db):
    add_product(db, 1, quantity_received=10, name="Keep me")

    response = submit_edit_form(client, name="Changed",
                                headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert stored(db)["name"] == "Keep me"


# Recording a sale ------------------------------------------------------------

def sale_form_of(client, product_id=1):
    page = client.get(f"/products/{product_id}/sell").text
    posts = [form for form in forms(page) if form["method"] == "post"]

    return page, (posts[0] if posts else None)


def submit_sale_form(client, product_id=1, follow_redirects=False,
                     headers=None, **typed):
    _, form = sale_form_of(client, product_id)
    data = form_data(form)
    data.update(typed)

    return client.post(form["action"], data=data, headers=headers or {},
                       follow_redirects=follow_redirects)


def sales_stored(db):
    return [dict(row) for row in db.execute("SELECT * FROM sales ORDER BY id")]


def test_only_a_product_with_stock_offers_sell(client, db):
    add_product(db, 1, quantity_received=2)
    add_product(db, 2, quantity_received=2)
    add_sale(db, 1, item_id=2, quantity=2)

    rows = {row[ID]: row for row in table_rows(client.get("/").text)}
    out = {row[ID]: row for row in table_rows(client.get("/out-of-stock").text)}

    assert rows.keys() == {"1"}
    assert rows["1"][ACTIONS] == "Sell Return Edit"
    assert out.keys() == {"2"}
    assert out["2"][OUT_ACTIONS] == "Edit"


def test_the_sale_form_offers_the_fields_the_reader_reads(client, db):
    add_product(db, 1, quantity_received=5)

    _, form = sale_form_of(client)

    assert form["action"].endswith("/products/1/sell")
    assert field_names(form) == set(psells.SALE_FORM_FIELDS)
    assert set(web.SaleForm.model_fields) == set(psells.SALE_FORM_FIELDS)
    assert form_data(form) == {"quantity": "1", "sale_price": "",
                               "date": date.today().isoformat()}
    assert field(form, "date")["type"] == "date"


def test_the_sale_form_shows_the_cut_the_api_serves(client, db):
    """The figure on the page is the one that will be frozen onto the sale."""
    add_product(db, 1, quantity_received=5, partner_share_mode="custom_percent",
                partner_share_percent=12.5, retail_price_cents=10003)

    page, _ = sale_form_of(client)
    served = client.get("/products").json()[0]

    assert figures(page)["Partner cut per unit"] == psells.format_cents(
        served["partner_share_cents"])
    assert figures(page)["Available"] == str(served["quantity_available"])


def test_a_sale_answers_303_and_is_stored_with_its_frozen_cut(client, db):
    add_product(db, 1, quantity_received=5)

    response = submit_sale_form(client, quantity="2", sale_price="85.50",
                                date="2026-09-20")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/?sold=1")
    stored = sales_stored(db)
    assert stored == [{
        "id": stored[0]["id"], "date": date(2026, 9, 20), "item_id": 1,
        "quantity": 2, "sale_price_cents": 8550, "partner_share_cents": 4000,
    }]


def test_after_a_sale_the_stock_and_the_dashboard_move(client, db):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    page = submit_sale_form(client, follow_redirects=True, quantity="2",
                            sale_price="90.00").text

    assert "Recorded a sale of Jordan 1 Chicago, id 1." in page
    assert table_rows(page)[0][AVAILABLE] == "3"
    assert figures(page)["Total revenue"] == "$180.00"


def test_the_form_records_what_the_api_would(client, db):
    """The same sale by both front doors, the same row apart from the id."""
    add_product(db, 1, quantity_received=5)

    submit_sale_form(client, quantity="2", sale_price="85.50",
                     date="2026-09-20")
    client.post("/sales", json={"item_id": 1, "quantity": 2,
                                "sale_price_cents": 8550,
                                "date": "2026-09-20"})

    first, second = sales_stored(db)
    first.pop("id")
    second.pop("id")

    assert first == second


def test_a_blank_date_means_today(client, db):
    add_product(db, 1, quantity_received=5)

    submit_sale_form(client, sale_price="90.00", date="")

    assert sales_stored(db)[0]["date"] == date.today()


def test_a_date_without_leading_zeros_is_stored_as_that_day(client, db):
    """2026-9-3 is a real date, and the page stores it as that day, as the
    command line does."""
    add_product(db, 1, quantity_received=5)

    response = submit_sale_form(client, sale_price="90.00", date="2026-9-3")

    assert response.status_code == 303
    assert sales_stored(db)[0]["date"] == date(2026, 9, 3)


@pytest.mark.parametrize("typed, field_name", [
    ({"sale_price": ""}, "sale_price"),
    ({"sale_price": "9O"}, "sale_price"),
    ({"sale_price": "-1.00"}, "sale_price"),
    ({"sale_price": "90", "quantity": "0"}, "quantity"),
    ({"sale_price": "90", "quantity": "two"}, "quantity"),
    ({"sale_price": "90", "date": "2026-02-30"}, "date"),
])
def test_input_wrong_in_itself_is_a_422(client, db, typed, field_name):
    add_product(db, 1, quantity_received=5)

    response = submit_sale_form(client, **typed)

    assert response.status_code == 422
    assert sales_stored(db) == []
    assert field(forms(response.text)[-1], field_name)["aria-invalid"] == "true"


def test_selling_more_than_is_available_is_a_409(client, db):
    """Well formed, and the stock disagrees: create_sale's own sentence,
    beside the quantity, with what was typed kept."""
    add_product(db, 1, quantity_received=3)

    response = submit_sale_form(client, quantity="5", sale_price="90.00")
    form = forms(response.text)[-1]

    assert response.status_code == 409
    assert sales_stored(db) == []
    assert "Only 3 available, so 5 cannot be sold." in response.text
    assert form_data(form)["quantity"] == "5"
    assert form_data(form)["sale_price"] == "90.00"


def test_a_sold_out_product_has_no_form_and_refuses_a_post(client, db):
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1)

    page, form = sale_form_of(client)

    assert form is None
    assert "No stock available to sell." in page

    response = client.post("/products/1/sell",
                           data={"quantity": "1", "sale_price": "90"})

    assert response.status_code == 409
    assert len(sales_stored(db)) == 1


def test_selling_a_product_that_does_not_exist_is_a_404(client, db):
    for method in ("get", "post"):
        response = getattr(client, method)("/products/99/sell")

        assert response.status_code == 404
        assert "No product 99" in response.text

    assert client.get("/products/abc/sell").status_code == 404


def test_a_sale_from_another_site_is_refused(client, db):
    add_product(db, 1, quantity_received=5)

    response = submit_sale_form(client, sale_price="90.00",
                                headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert sales_stored(db) == []


# Recording a return ----------------------------------------------------------

def return_form_of(client, product_id=1):
    page = client.get(f"/products/{product_id}/return").text
    posts = [form for form in forms(page) if form["method"] == "post"]

    return page, (posts[0] if posts else None)


def submit_return_form(client, product_id=1, follow_redirects=False,
                       headers=None, **typed):
    _, form = return_form_of(client, product_id)
    data = form_data(form)
    data.update(typed)

    return client.post(form["action"], data=data, headers=headers or {},
                       follow_redirects=follow_redirects)


def returns_stored(db):
    return [dict(row) for row in db.execute("SELECT * FROM returns ORDER BY id")]


def test_the_return_form_offers_the_fields_the_reader_reads(client, db):
    add_product(db, 1, quantity_received=5)

    _, form = return_form_of(client)

    assert form["action"].endswith("/products/1/return")
    assert field_names(form) == set(psells.RETURN_FORM_FIELDS)
    assert set(web.ReturnForm.model_fields) == set(psells.RETURN_FORM_FIELDS)
    assert form_data(form) == {"quantity": "1",
                               "date": date.today().isoformat(), "notes": ""}


def test_a_return_answers_303_and_is_stored(client, db):
    add_product(db, 1, quantity_received=5, name="Jordan 1 Chicago")

    response = submit_return_form(client, quantity="2", date="2026-9-3",
                                  notes="damaged box")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/?returned=1")
    stored = returns_stored(db)
    assert stored == [{"id": stored[0]["id"], "date": date(2026, 9, 3),
                       "item_id": 1, "quantity": 2, "notes": "damaged box"}]
    assert "Recorded a return of Jordan 1 Chicago, id 1." in client.get(
        response.headers["location"]).text


def test_a_return_moves_stock_and_no_money(client, db):
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=1, sale_price_cents=9000,
             partner_share_cents=3500)
    before = figures(client.get("/").text)

    page = submit_return_form(client, follow_redirects=True, quantity="2").text
    after = figures(page)

    assert table_rows(page)[0][AVAILABLE] == "2"
    assert after["Total returned"] == "2"
    assert after["Total available"] == "2"
    for label in ("Total revenue", "Total profit", "Total partner share earned",
                  "Total paid", "Balance owing", "Total received",
                  "Total sold"):
        assert after[label] == before[label], label


@pytest.mark.parametrize("typed, field_name", [
    ({"quantity": ""}, "quantity"),
    ({"quantity": "0"}, "quantity"),
    ({"quantity": "1.5"}, "quantity"),
    ({"date": "2026-02-30"}, "date"),
])
def test_return_input_wrong_in_itself_is_a_422(client, db, typed, field_name):
    add_product(db, 1, quantity_received=5)

    response = submit_return_form(client, **typed)

    assert response.status_code == 422
    assert returns_stored(db) == []
    assert field(forms(response.text)[-1], field_name)["aria-invalid"] == "true"


def test_returning_more_than_is_available_is_a_409(client, db):
    add_product(db, 1, quantity_received=3)

    response = submit_return_form(client, quantity="5", notes="kept")

    assert response.status_code == 409
    assert returns_stored(db) == []
    assert "Only 3 available, so 5 cannot be returned." in response.text
    assert form_data(forms(response.text)[-1])["notes"] == "kept"


def test_a_product_with_no_stock_has_no_return_form(client, db):
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1)

    page, form = return_form_of(client)

    assert form is None
    assert "No stock available to return." in page
    assert client.post("/products/1/return",
                       data={"quantity": "1"}).status_code == 409


def test_returning_a_product_that_does_not_exist_is_a_404(client, db):
    for method in ("get", "post"):
        assert getattr(client, method)("/products/99/return").status_code == 404

    assert client.get("/products/abc/return").status_code == 404


def test_a_return_from_another_site_is_refused(client, db):
    add_product(db, 1, quantity_received=5)

    response = submit_return_form(client,
                                  headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert returns_stored(db) == []


# Recording a payment ---------------------------------------------------------

def payment_form_of(client):
    (form,) = [form for form in forms(client.get("/payments/new").text)
               if form["method"] == "post"]

    return form


def submit_payment_form(client, follow_redirects=False, headers=None,
                        **typed):
    form = payment_form_of(client)
    data = form_data(form)
    data.update(typed)

    return client.post(form["action"], data=data, headers=headers or {},
                       follow_redirects=follow_redirects)


def payments_stored(db):
    return [dict(row) for row in db.execute("SELECT * FROM payments ORDER BY id")]


def test_the_payment_page_is_linked_from_the_nav_and_the_panel(client):
    page = client.get("/").text

    assert page.count('href="http://testserver/payments/new"') == 2


def test_the_payment_form_offers_the_fields_the_reader_reads(client):
    form = payment_form_of(client)

    assert form["action"].endswith("/payments/new")
    assert field_names(form) == set(psells.PAYMENT_FORM_FIELDS)
    assert set(web.PaymentForm.model_fields) == set(psells.PAYMENT_FORM_FIELDS)
    assert form_data(form) == {"amount": "", "date": date.today().isoformat(),
                               "notes": ""}


def test_the_payment_page_shows_the_balance_the_api_serves(client, db):
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=2, sale_price_cents=9000,
             partner_share_cents=3500)
    add_payment(db, 1, amount_cents=2000)

    shown = figures(client.get("/payments/new").text)
    served = client.get("/dashboard").json()

    assert shown == {
        "Total partner share earned":
            psells.format_cents(served["total_partner_share_cents"]),
        "Total paid": psells.format_cents(served["total_paid_cents"]),
        "Balance owing": psells.format_cents(served["balance_owing_cents"]),
    }


def test_a_payment_answers_303_and_is_stored(client, db):
    response = submit_payment_form(client, amount="150.00", date="2026-9-14",
                                   notes="e-transfer")

    stored = payments_stored(db)
    payment_id = stored[0]["id"]

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/?paid={payment_id}")
    assert stored == [{"id": payment_id, "date": date(2026, 9, 14),
                       "amount_cents": 15000, "notes": "e-transfer"}]
    assert "Recorded a payment of $150.00 dated 2026-09-14." in client.get(
        response.headers["location"]).text


def test_a_payment_moves_only_paid_and_the_balance_on_the_page(client, db):
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=2, sale_price_cents=9000,
             partner_share_cents=3500)
    before = figures(client.get("/").text)

    after = figures(submit_payment_form(client, follow_redirects=True,
                                        amount="50.00").text)

    assert after["Total paid"] == "$50.00"
    assert after["Balance owing"] == "$20.00"
    for label in before:
        if label not in ("Total paid", "Balance owing"):
            assert after[label] == before[label], label


def test_an_overpayment_shows_a_negative_balance(client, db):
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=1, sale_price_cents=2000,
             partner_share_cents=500)

    page = submit_payment_form(client, follow_redirects=True,
                               amount="8.00").text

    assert figures(page)["Balance owing"] == "-$3.00"


def test_the_form_records_what_the_command_lines_function_would(client, db):
    submit_payment_form(client, amount="12.50", date="2026-09-14", notes="n")
    psells.create_payment(db, 1250, "2026-09-14", "n")

    first, second = payments_stored(db)
    first.pop("id")
    second.pop("id")

    assert first == second


def test_a_payment_of_zero_is_accepted_from_the_page(client, db):
    assert submit_payment_form(client, amount="0").status_code == 303
    assert payments_stored(db)[0]["amount_cents"] == 0


@pytest.mark.parametrize("typed, field_name", [
    ({"amount": ""}, "amount"),
    ({"amount": "abc"}, "amount"),
    ({"amount": "12.505"}, "amount"),
    ({"amount": "-5.00"}, "amount"),
    ({"amount": "5", "date": "2026-13-01"}, "date"),
])
def test_payment_input_wrong_in_itself_is_a_422(client, db, typed,
                                                field_name):
    response = submit_payment_form(client, notes="kept", **typed)
    form = forms(response.text)[-1]

    assert response.status_code == 422
    assert payments_stored(db) == []
    assert field(form, field_name)["aria-invalid"] == "true"
    assert form_data(form)["notes"] == "kept"


def test_the_payment_notice_names_only_a_payment_that_exists(client, db):
    """With a payment present, so the lookup actually runs for each value."""
    add_payment(db, 1, amount_cents=15000)

    for paid in ["999", "abc", "1.0", ""]:
        page = client.get("/", params={"paid": paid})

        assert page.status_code == 200, paid
        assert "Recorded a payment" not in page.text, paid

    assert "Recorded a payment of $150.00" in client.get(
        "/", params={"paid": "1"}).text


def test_a_payment_from_another_site_is_refused(client, db):
    response = submit_payment_form(client, amount="100.00",
                                   headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert payments_stored(db) == []


# Deleting a product ----------------------------------------------------------

def delete_form_of(client, product_id=1):
    page = client.get(f"/products/{product_id}/delete").text
    posts = [form for form in forms(page) if form["method"] == "post"]

    return page, (posts[0] if posts else None)


def test_delete_is_offered_from_the_edit_page_not_the_inventory(client, db):
    """Rare and permanent, so one step further away than Sell or Edit."""
    add_product(db, 1, quantity_received=1)

    assert "/products/1/delete" in client.get("/products/1/edit").text
    assert "/delete" not in client.get("/").text
    assert "/delete" not in client.get("/products/new").text


def test_a_product_with_no_history_is_offered_a_delete_button(client, db):
    add_product(db, 1, quantity_received=1)

    page, form = delete_form_of(client)

    assert form["action"].endswith("/products/1/delete")
    assert "there is no undo" in page


def test_deleting_answers_303_and_the_product_is_gone(client, db):
    add_product(db, 1, quantity_received=1, name="Typo product")
    add_product(db, 2, quantity_received=1, name="Keeper")
    _, form = delete_form_of(client)

    response = client.post(form["action"], data=form_data(form),
                           follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "http://testserver/"
    assert [row[NAME] for row in table_rows(client.get("/").text)] == ["Keeper"]


def test_a_product_with_history_gets_the_reason_and_no_button(client, db):
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=2)
    add_return(db, 1, item_id=1, quantity=1)

    page, form = delete_form_of(client)

    assert form is None
    assert ("This product has 1 sale and 1 return recorded against it."
            in page)


def test_posting_a_delete_for_a_product_with_history_is_a_409(client, db):
    """No button is offered, but a post can still arrive. It is refused with
    the same sentence, and the product and its sale remain."""
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=1)

    response = client.post("/products/1/delete")

    assert response.status_code == 409
    assert "This product has 1 sale recorded against it." in response.text
    assert db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 1
    assert db.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"] == 1


def test_deleting_a_product_that_does_not_exist_is_a_404(client, db):
    for method in ("get", "post"):
        assert getattr(client, method)("/products/99/delete").status_code == 404

    assert client.get("/products/abc/delete").status_code == 404


def test_a_delete_from_another_site_is_refused(client, db):
    add_product(db, 1, quantity_received=1)

    response = client.post("/products/1/delete",
                           headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 1


def test_a_delete_link_alone_deletes_nothing(client, db):
    """Visiting the page, which a prefetch or a link preview might, only
    shows the question."""
    add_product(db, 1, quantity_received=1)

    client.get("/products/1/delete")

    assert db.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 1


# The dashboard panel ---------------------------------------------------------

# The labels the command line prints, paired with the key /dashboard serves
# each figure under. Money is in cents in the API and formatted on the page.
DASHBOARD = {
    "Total received": "total_received",
    "Total sold": "total_sold",
    "Total available": "total_available",
    "Total returned": "total_returned",
    "Total revenue": "total_revenue_cents",
    "Total profit": "total_profit_cents",
    "Total partner share earned": "total_partner_share_cents",
    "Total paid": "total_paid_cents",
    "Balance owing": "balance_owing_cents",
}


def test_the_dashboard_is_all_zeros_on_an_empty_database(client):
    shown = figures(client.get("/").text)

    assert shown == {
        "Total received": "0",
        "Total sold": "0",
        "Total available": "0",
        "Total returned": "0",
        "Total revenue": "$0.00",
        "Total profit": "$0.00",
        "Total partner share earned": "$0.00",
        "Total paid": "$0.00",
        "Balance owing": "$0.00",
    }


def test_the_dashboard_figures(client, db):
    """Ten received, four sold at 90.00 with a 35.00 cut, one returned, 50.00
    paid. Revenue 360.00, partner share 140.00, profit 220.00, owing 90.00."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=4,
             sale_price_cents=9000, partner_share_cents=3500)
    add_return(db, 1, item_id=1, quantity=1)
    add_payment(db, 1, amount_cents=5000)

    shown = figures(client.get("/").text)

    assert shown["Total received"] == "10"
    assert shown["Total sold"] == "4"
    assert shown["Total available"] == "5"
    assert shown["Total returned"] == "1"
    assert shown["Total revenue"] == "$360.00"
    assert shown["Total partner share earned"] == "$140.00"
    assert shown["Total profit"] == "$220.00"
    assert shown["Total paid"] == "$50.00"
    assert shown["Balance owing"] == "$90.00"


def test_an_overpaid_partner_shows_a_negative_balance(client, db):
    """The case the sign fix was for, now where a person will see it."""
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1,
             sale_price_cents=2000, partner_share_cents=500)
    add_payment(db, 1, amount_cents=800)

    assert figures(client.get("/").text)["Balance owing"] == "-$3.00"


def test_the_dashboard_shows_the_figures_the_api_serves(client, db):
    """All nine, against /dashboard, on a database with something in it."""
    add_product(db, 1, quantity_received=10)
    add_product(db, 2, quantity_received=3,
                partner_share_mode="custom_amount",
                partner_share_amount_cents=1234)
    add_sale(db, 1, item_id=1, quantity=4,
             sale_price_cents=9001, partner_share_cents=3600)
    add_sale(db, 2, item_id=2, quantity=2,
             sale_price_cents=5000, partner_share_cents=1234)
    add_return(db, 1, item_id=1, quantity=1)
    add_payment(db, 1, amount_cents=20000)

    served = client.get("/dashboard").json()
    shown = figures(client.get("/").text)

    assert shown.keys() == DASHBOARD.keys()

    for label, key in DASHBOARD.items():
        if key.endswith("_cents"):
            assert shown[label] == psells.format_cents(served[key]), label
        else:
            assert shown[label] == str(served[key]), label


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
    add_product(db, 5, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=4)
    add_sale(db, 2, item_id=5, quantity=1)
    add_return(db, 1, item_id=3, quantity=1)

    served = {p["id"]: p for p in client.get("/products/in-stock").json()}
    shown = {int(row[ID]): row for row in table_rows(client.get("/").text)}

    assert shown.keys() == served.keys() == {1, 2, 3, 4}

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
    assert set(paths) == {"/products", "/products/in-stock",
                          "/products/out-of-stock", "/dashboard", "/sales",
                          "/returns", "/payments", "/session"}


# Templates format and never compute -----------------------------------------
#
# The third rule, enforced by reading the templates the way Jinja2 does rather
# than by searching them as text. A template that recomputes a figure correctly
# passes every comparison against the API, because it agrees today; this is
# what stops the second copy existing at all.

ARITHMETIC = (nodes.Add, nodes.Sub, nodes.Mul, nodes.Div, nodes.FloorDiv,
              nodes.Mod, nodes.Pow, nodes.Neg)

# Every filter a template may use. Adding one here is a decision, and the
# question to ask is whether it formats or computes.
ALLOWED_FILTERS = {"money"}


def every_template():
    """Each template's name and the tree Jinja2 parses it into."""
    environment = web.templates.env

    for name in environment.list_templates():
        source = environment.loader.get_source(environment, name)[0]
        yield name, environment.parse(source)


def test_there_are_templates_to_check():
    """So the two tests below cannot pass by finding nothing."""
    names = [name for name, _ in every_template()]

    assert "base.html" in names
    assert "inventory.html" in names
    assert "product_form.html" in names
    assert "sale_form.html" in names
    assert "return_form.html" in names
    assert "payment_form.html" in names
    assert "delete_confirm.html" in names
    assert "out_of_stock.html" in names
    assert "sales_history.html" in names
    assert "returns_history.html" in names
    assert "payments_history.html" in names
    assert "record_edit.html" in names
    assert "record_delete.html" in names
    assert "record_not_found.html" in names
    assert "macros.html" in names


def test_no_template_does_arithmetic():
    for name, tree in every_template():
        found = [type(node).__name__ for node in tree.find_all(ARITHMETIC)]

        assert found == [], f"{name} computes: {found}"


def test_templates_use_only_the_allowed_filters():
    for name, tree in every_template():
        used = {node.name for node in tree.find_all(nodes.Filter)}

        assert used <= ALLOWED_FILTERS, (
            f"{name} uses {sorted(used - ALLOWED_FILTERS)}"
        )
