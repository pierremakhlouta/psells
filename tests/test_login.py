"""Tests for the login: every route refuses without a session, and the login
and logout pages themselves.

The first test is the one the phase rests on. It does not list the routes; it
asks the application for them and calls every one without a session, so a
route added later is tested the day it is added. Its companion checks the
application has no route outside the three routers PSells owns, so nothing can
be reached without passing one of their checks.

The anonymous client speaks https, as the browser does to nginx, because the
session cookie is Secure and a client sends it back only over https.
"""

import datetime
import re

import pytest

import api
import auth
import web
from dependencies import SESSION_COOKIE
from helpers import (
    TEST_PASSWORD, TEST_USERNAME, add_product, add_user, forms, log_in)


def every_route(router):
    """(method, path) for every route on one router, with a real id in paths
    that take one, so the route itself answers rather than a 404."""
    return [
        (method, re.sub(r"\{\w+:int\}", "1", route.path))
        for route in router.routes
        for method in sorted(route.methods)
    ]


PAGES = every_route(web.router)
ENDPOINTS = every_route(api.protected)


def sessions(db):
    return db.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]


def rows(db):
    return {table: db.execute(f"SELECT COUNT(*) AS n FROM {table}")
            .fetchone()["n"]
            for table in ("products", "sales", "returns", "payments",
                          "corrections")}


def log_in_through_the_page(client, username=TEST_USERNAME,
                            password=TEST_PASSWORD):
    return client.post("/login", data={"username": username,
                                       "password": password},
                       follow_redirects=False)


# Nothing without a session ---------------------------------------------------------

def test_the_walk_finds_the_routes_it_should():
    # If the walk found nothing, every test below would pass by testing
    # nothing.
    assert ("GET", "/") in PAGES
    assert ("POST", "/products/1/sell") in PAGES
    assert ("POST", "/logout") in PAGES
    assert ("POST", "/sales") in ENDPOINTS
    assert ("GET", "/openapi.json") in ENDPOINTS


@pytest.mark.parametrize("method, path", PAGES)
def test_every_page_sends_you_to_log_in(anonymous, db, method, path):
    add_product(db, 1, quantity_received=5)
    before = rows(db)

    response = anonymous.request(method, path, follow_redirects=False,
                                 data={"quantity": "1", "sale_price": "90",
                                       "amount": "10", "name": "x"})

    assert response.status_code == 303
    assert response.headers["location"] == "https://testserver/login"
    assert rows(db) == before


@pytest.mark.parametrize("method, path", ENDPOINTS)
def test_every_endpoint_answers_401(anonymous, db, method, path):
    add_product(db, 1, quantity_received=5)
    before = rows(db)

    response = anonymous.request(method, path, json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 9000})

    assert response.status_code == 401
    assert response.json() == {"detail": "Log in first."}
    assert rows(db) == before


def test_the_application_has_no_route_outside_the_three_routers():
    # FastAPI 0.141 keeps each included router as one entry of app.routes,
    # holding the router it was given. Any other entry is a route added
    # straight onto the application, which no router's check covers. If a
    # FastAPI upgrade changes this shape, this fails rather than passing.
    included = [getattr(route, "original_router", None)
                for route in api.app.routes]

    assert included == [api.protected, web.router, web.public]


def test_only_the_login_page_is_public():
    assert every_route(web.public) == [("GET", "/login"), ("POST", "/login")]


def test_an_expired_session_is_sent_to_log_in(anonymous, db, monkeypatch):
    cookie_value, _ = log_in(db)
    anonymous.cookies.set(SESSION_COOKIE, cookie_value)
    assert anonymous.get("/", follow_redirects=False).status_code == 200

    later = auth.now() + auth.IDLE_LIMIT + datetime.timedelta(seconds=1)
    monkeypatch.setattr(auth, "now", lambda: later)

    response = anonymous.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "https://testserver/login"


def test_a_made_up_cookie_is_no_session(anonymous, db):
    log_in(db)
    anonymous.cookies.set(SESSION_COOKIE, "made up")

    assert anonymous.get("/products").status_code == 401


# The login page -------------------------------------------------------------------

def test_the_login_page_links_to_nothing_behind_the_login(anonymous):
    page = anonymous.get("/login")

    assert page.status_code == 200
    assert 'action="https://testserver/login"' in page.text
    assert 'autocomplete="current-password"' in page.text
    assert "Record payment" not in page.text
    assert "/logout" not in page.text


def test_logging_in_sets_the_cookie_and_opens_the_inventory(anonymous, db):
    add_user(db)

    response = log_in_through_the_page(anonymous)

    assert response.status_code == 303
    assert response.headers["location"] == "https://testserver/"
    assert anonymous.get("/", follow_redirects=False).status_code == 200
    assert sessions(db) == 1


def test_the_cookie_is_host_only_secure_httponly_and_lax(anonymous, db):
    add_user(db)

    cookie = log_in_through_the_page(anonymous).headers["set-cookie"]
    attributes = {part.strip().split("=")[0].lower()
                  for part in cookie.split(";")[1:]}

    assert cookie.startswith(SESSION_COOKIE + "=")
    assert {"httponly", "secure", "path", "samesite", "max-age"} <= attributes
    assert "domain" not in attributes
    assert "Path=/;" in cookie + ";"
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie


def test_the_cookie_holds_what_the_session_is_found_by(anonymous, db):
    add_user(db)

    cookie = log_in_through_the_page(anonymous).headers["set-cookie"]
    value = re.match(rf"{SESSION_COOKIE}=([^;]+)", cookie).group(1)

    assert auth.find_session(db, value, auth.now()) is not None


@pytest.mark.parametrize("username, password", [
    (TEST_USERNAME, "the wrong passphrase"),
    ("nobody", TEST_PASSWORD),
    ("", ""),
])
def test_a_failed_login_says_the_same_thing_and_sets_nothing(
        anonymous, db, username, password):
    add_user(db)

    response = log_in_through_the_page(anonymous, username, password)

    assert response.status_code == 401
    assert "The username or password is wrong." in response.text
    assert "set-cookie" not in response.headers
    assert sessions(db) == 0


def test_a_failed_login_keeps_the_username_but_never_the_password(
        anonymous, db):
    add_user(db)

    response = log_in_through_the_page(anonymous, TEST_USERNAME,
                                       "the wrong passphrase")

    assert f'value="{TEST_USERNAME}"' in response.text
    assert "the wrong passphrase" not in response.text


def test_someone_logged_in_is_sent_past_the_login_page(anonymous, db):
    cookie_value, _ = log_in(db)
    anonymous.cookies.set(SESSION_COOKIE, cookie_value)

    response = anonymous.get("/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://testserver/"


def test_logging_in_ends_the_session_the_browser_had(anonymous, db):
    # A cookie someone planted before the login must be worthless after it.
    planted, _ = log_in(db)
    anonymous.cookies.set(SESSION_COOKIE, planted)

    log_in_through_the_page(anonymous)

    assert auth.find_session(db, planted, auth.now()) is None
    assert sessions(db) == 1


def test_a_login_posted_from_another_site_is_refused(anonymous, db):
    add_user(db)

    response = anonymous.post(
        "/login", data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
        headers={"Sec-Fetch-Site": "cross-site"}, follow_redirects=False)

    assert response.status_code == 403
    assert sessions(db) == 0


# Logging out ----------------------------------------------------------------------

def test_every_page_behind_the_login_has_a_log_out_button(client):
    page = client.get("/").text

    assert '<form class="logout" action="http://testserver/logout" ' \
           'method="post">' in page


def test_logging_out_ends_the_session_and_clears_the_cookie(anonymous, db):
    add_user(db)
    log_in_through_the_page(anonymous)
    kept = anonymous.cookies[SESSION_COOKIE]

    # Pressed as a browser would: the header's form, with its hidden token.
    (button,) = forms(anonymous.get("/").text, with_logout=True)[:1]
    token = {field["name"]: field["value"] for field in button["inputs"]}
    response = anonymous.post(button["action"], data=token,
                              follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://testserver/login"
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f'{SESSION_COOKIE}=""')
    assert "Max-Age=0" in cleared and "Secure" in cleared
    assert sessions(db) == 0

    # The value itself, replayed after logging out, opens nothing.
    anonymous.cookies.set(SESSION_COOKIE, kept)
    assert anonymous.get("/products").status_code == 401


def test_logging_out_is_not_a_link(client):
    assert client.get("/logout").status_code == 405
