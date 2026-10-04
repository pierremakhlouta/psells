"""Tests for the form token: every form carries it, and every write needs it.

Like tests/test_login.py, these do not list the forms or the routes. They read
every template, render every page, and call every route that writes, so a form
or a route added later is covered the day it is added.

The shared client sends the token in the X-Form-Token header, as a program
would. The pages' own way, the hidden field and no header, is tested here with
a client that has the cookie and nothing else.
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

import api
import auth
import dependencies
import web
from helpers import (add_payment, add_product, add_return, add_sale, forms,
                     log_in)


TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(web.__file__)),
                         "templates")

# The one form behind no login, so with no session and no token. The browser-
# label check in cross_site.py covers it; tests/test_login.py tests that.
TOKENLESS = {"login.html"}


def rows(db):
    return {table: db.execute(f"SELECT COUNT(*) AS n FROM {table}")
            .fetchone()["n"]
            for table in ("products", "sales", "returns", "payments",
                          "sessions", "corrections")}


def routes(router, methods):
    return [
        (method, re.sub(r"\{\w+:int\}", "1", route.path))
        for route in router.routes
        for method in sorted(route.methods)
        if method in methods
    ]


WRITES = (routes(web.router, {"POST"})
          + routes(api.protected, {"POST", "PUT", "PATCH", "DELETE"}))
PAGES = routes(web.router, {"GET"})


@pytest.fixture
def stock(db):
    """Product 1 with units left, and sale 1, return 1 and payment 1, so every
    page with an id in its path has a record to show, and every write one to
    change."""
    add_product(db, 1, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=1)
    add_return(db, 1, item_id=1, quantity=1)
    add_payment(db, 1, 100)


@pytest.fixture
def browser(db, partner_rate):
    """A logged-in client that sends the cookie and nothing else: no
    X-Form-Token header, so a write succeeds only with the hidden field."""
    api.app.dependency_overrides[dependencies.get_connection] = lambda: db
    cookie_value, form_token = log_in(db)

    client = TestClient(api.app,
                        cookies={dependencies.SESSION_COOKIE: cookie_value})
    client.form_token = form_token
    yield client

    api.app.dependency_overrides.clear()


# Every form carries it -----------------------------------------------------------

def template(name):
    with open(os.path.join(TEMPLATES, name)) as source:
        return source.read()


def posting_forms_in(template_text):
    """The source of every <form ... method="post"> ... </form> in a template."""
    return re.findall(r'<form\b[^>]*method="post"[^>]*>.*?</form>',
                      template_text, flags=re.S | re.I)


def test_the_template_check_finds_the_forms_it_should():
    found = {name for name in os.listdir(TEMPLATES)
             if posting_forms_in(template(name))}

    assert {"base.html", "sale_form.html", "product_form.html",
            "login.html"} <= found


@pytest.mark.parametrize("name", sorted(
    name for name in os.listdir(TEMPLATES) if name not in TOKENLESS))
def test_every_posting_form_in_the_templates_carries_the_token(name):
    for form in posting_forms_in(template(name)):
        assert "{{ form_token() }}" in form, f"{name}: {form[:80]}"


def test_the_template_check_covers_every_template_it_skips():
    # Skipping a template is a decision, so it is listed, and the list may
    # hold only templates that exist.
    assert TOKENLESS <= set(os.listdir(TEMPLATES))


@pytest.mark.parametrize("method, path", PAGES)
def test_every_rendered_form_that_posts_holds_this_sessions_token(
        browser, stock, method, path):
    page = browser.get(path)
    assert page.status_code == 200

    posting = [form for form in forms(page.text, with_logout=True)
               if form["method"] == "post"]
    # At least the header's Log out button, on every page.
    assert posting

    for form in posting:
        tokens = [field for field in form["inputs"]
                  if field.get("name") == dependencies.FORM_TOKEN_FIELD]
        assert len(tokens) == 1, form["action"]
        assert tokens[0]["type"] == "hidden"
        assert tokens[0]["value"] == browser.form_token


# Every write needs it -------------------------------------------------------------

def test_the_walk_finds_the_writes_it_should():
    assert ("POST", "/products/1/sell") in WRITES
    assert ("POST", "/logout") in WRITES
    assert ("POST", "/sales") in WRITES
    for kind in ("sales", "returns", "payments"):
        assert ("POST", f"/{kind}-history/1/edit") in WRITES
        assert ("POST", f"/{kind}-history/1/delete") in WRITES


@pytest.mark.parametrize("method, path", WRITES)
@pytest.mark.parametrize("token", [None, "", "a guess"])
def test_every_write_without_the_right_token_is_refused(
        browser, db, stock, method, path, token):
    before = rows(db)
    headers = {} if token is None else {dependencies.FORM_TOKEN_HEADER: token}

    response = browser.request(
        method, path, headers=headers, follow_redirects=False,
        data={"quantity": "1", "sale_price": "90", "amount": "10",
              "name": "x"})

    assert response.status_code == 403
    assert response.text.startswith("Refused: the form token")
    assert rows(db) == before


@pytest.mark.parametrize("method, path", WRITES)
def test_another_sessions_token_is_refused(browser, db, stock, method, path):
    _, someone_elses = auth.start_session(
        db, db.execute("SELECT id FROM users").fetchone()["id"], auth.now())
    before = rows(db)

    response = browser.request(
        method, path, follow_redirects=False,
        headers={dependencies.FORM_TOKEN_HEADER: someone_elses})

    assert response.status_code == 403
    assert rows(db) == before


def test_a_page_form_goes_through_with_its_hidden_field(browser, db, stock):
    (form,) = [form for form in forms(browser.get("/products/1/sell").text)
               if form["method"] == "post"]
    data = {field["name"]: field.get("value") or ""
            for field in form["inputs"] if "name" in field}
    data.update(quantity="1", sale_price="90")
    before = rows(db)["sales"]

    response = browser.post(form["action"], data=data, follow_redirects=False)

    assert response.status_code == 303
    assert rows(db)["sales"] == before + 1


def test_a_program_gets_the_token_and_sends_it_as_a_header(browser, db, stock):
    token = browser.get("/session").json()["form_token"]

    response = browser.post(
        "/sales", headers={dependencies.FORM_TOKEN_HEADER: token},
        json={"item_id": 1, "quantity": 1, "sale_price_cents": 9000})

    assert token == browser.form_token
    assert response.status_code == 201


def test_the_token_in_a_json_body_is_not_enough(browser, db, stock):
    before = rows(db)
    response = browser.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 9000,
        "form_token": browser.form_token})

    assert response.status_code == 403
    assert rows(db) == before


def test_reading_needs_no_token(browser, stock):
    assert browser.get("/?q=Product").status_code == 200
    assert browser.get("/products").status_code == 200


def test_without_a_session_the_answer_is_log_in_not_the_token(anonymous, db):
    # The session is checked first: a stranger is told to log in, not given a
    # hint about tokens.
    response = anonymous.post("/products/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")
