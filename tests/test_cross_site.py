"""Tests for refusing writes a browser sends on behalf of another site.

The check wraps the whole application, so these drive it through the API's
POST /sales, the one write that exists today. Every form added later passes
through the same check, and its own tests say so.

A refused request must stop before the route runs, so every refusal here also
asserts that nothing was stored.
"""

import pytest

import cross_site

from helpers import add_product


THIS_SITE = "http://testserver"


def sales_count(db):
    return db.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]


def sell(client, headers):
    return client.post(
        "/sales",
        json={"item_id": 1, "quantity": 1, "sale_price_cents": 9000},
        headers=headers,
    )


@pytest.fixture
def stock(db):
    add_product(db, 1, quantity_received=5)


# Refused ---------------------------------------------------------------------

@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},
    {"Origin": "http://testserver:3000"},
    {"Origin": "https://testserver"},
    {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site"},
    {"Sec-Fetch-Site": "cross-site", "Origin": THIS_SITE},
])
def test_a_write_from_another_site_is_refused(client, db, stock, headers):
    """Including a claimed Origin of this site under a cross-site label: the
    label is set by the browser and a page cannot change it."""
    response = sell(client, headers)

    assert response.status_code == 403
    assert response.text.startswith("Refused: a write from another site.")
    assert sales_count(db) == 0


# Allowed ---------------------------------------------------------------------

@pytest.mark.parametrize("headers", [
    {},
    {"Origin": THIS_SITE},
    {"Sec-Fetch-Site": "same-origin"},
    {"Sec-Fetch-Site": "same-origin", "Origin": THIS_SITE},
    {"Sec-Fetch-Site": "none"},
])
def test_a_write_from_this_site_or_no_browser_goes_ahead(client, db, stock,
                                                          headers):
    response = sell(client, headers)

    assert response.status_code == 201
    assert sales_count(db) == 1


def test_reading_from_another_site_is_not_refused(client):
    """A read changes nothing, and other sites linking here is ordinary."""
    response = client.get("/products", headers={
        "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site",
    })

    assert response.status_code == 200


# The rule itself -------------------------------------------------------------

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post"])
def test_every_method_that_writes_is_checked(method):
    headers = {"origin": "https://evil.example"}

    assert cross_site.refusal(method, headers, "http", "127.0.0.1:8000")


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_methods_that_only_read_are_not_checked(method):
    headers = {"origin": "https://evil.example", "sec-fetch-site": "cross-site"}

    assert cross_site.refusal(method, headers, "http", "127.0.0.1:8000") is None


def test_the_origin_must_match_scheme_host_and_port_exactly():
    def check(origin):
        return cross_site.refusal("POST", {"origin": origin},
                                  "http", "127.0.0.1:8000")

    assert check("http://127.0.0.1:8000") is None
    assert check("http://127.0.0.1:8001")
    assert check("https://127.0.0.1:8000")
    assert check("http://localhost:8000")
