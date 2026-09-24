"""Tests for refusing writes a browser sends on behalf of another site.

The check wraps the whole application, so these drive it through the API's
POST /sales, the one write that exists today. Every form added later passes
through the same check, and its own tests say so.

A refused request must stop before the route runs, so every refusal here also
asserts that nothing was stored.
"""

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import api
import cross_site
import dependencies

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


# Behind nginx ----------------------------------------------------------------
#
# In the stack the browser speaks HTTPS to nginx, and nginx speaks plain HTTP
# to uvicorn, adding X-Forwarded-Proto: https. uvicorn wraps the application
# in ProxyHeadersMiddleware, which takes the scheme from that header only when
# the connection comes from an address in FORWARDED_ALLOW_IPS, and otherwise
# leaves it as http. These wrap the application the same way, with the real
# middleware, so the check sees exactly what it sees in the stack.
#
# The test client connects as "testclient", so trusting "testclient" stands for
# trusting nginx, and trusting only nginx's address in compose.yaml stands for
# a request that reached uvicorn some other way.

BEHIND_NGINX = "https://psells.localhost"
NGINX_ADDRESS = "10.213.47.10"


@pytest.fixture
def through(db, stock, partner_rate):
    """A test client whose requests arrive from a proxy uvicorn does or does
    not trust, over plain HTTP, as they do from nginx."""
    api.app.dependency_overrides[dependencies.get_connection] = lambda: db

    def client(trusted):
        return TestClient(ProxyHeadersMiddleware(api.app, trusted_hosts=trusted),
                          base_url="http://psells.localhost")

    yield client

    api.app.dependency_overrides.clear()


def test_a_write_over_https_goes_ahead_when_nginx_says_https(through, db):
    response = sell(through("testclient"), {
        "X-Forwarded-Proto": "https", "Origin": BEHIND_NGINX})

    assert response.status_code == 201
    assert sales_count(db) == 1


def test_without_the_forwarded_scheme_an_https_origin_looks_foreign(through,
                                                                    db):
    # Why nginx must send X-Forwarded-Proto: without it the app sees http,
    # and every write from a page served over https is refused.
    response = sell(through("testclient"), {"Origin": BEHIND_NGINX})

    assert response.status_code == 403
    assert sales_count(db) == 0


def test_a_forwarded_scheme_from_anyone_but_nginx_is_ignored(through, db):
    response = sell(through(NGINX_ADDRESS), {
        "X-Forwarded-Proto": "https", "Origin": BEHIND_NGINX})

    assert response.status_code == 403
    assert sales_count(db) == 0


def test_an_http_origin_is_another_site_once_the_page_is_https(through, db):
    response = sell(through("testclient"), {
        "X-Forwarded-Proto": "https", "Origin": "http://psells.localhost"})

    assert response.status_code == 403
    assert sales_count(db) == 0
