"""Tests for the HTTP API.

These drive the real application through a real request cycle, using FastAPI's
TestClient, which calls the app directly rather than opening a socket. The
database is the same in-memory one the other tests use, swapped in by overriding
the connection dependency, so no test touches a file. The client fixture that
does this lives in conftest.py.
"""

from datetime import date

import psells

from helpers import add_payment, add_product, add_return, add_sale


def test_products_is_empty_to_start_with(client):
    response = client.get("/products")

    assert response.status_code == 200
    assert response.json() == []


def test_a_product_is_served_with_every_field(client, db):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago",
                category="Shoes", notes="boxed")

    product = client.get("/products").json()[0]

    assert product["id"] == 1
    assert product["name"] == "Jordan 1 Chicago"
    assert product["category"] == "Shoes"
    assert product["condition"] == "Brand New"
    assert product["notes"] == "boxed"
    assert product["quantity_received"] == 10
    assert product["retail_price_cents"] == 10000
    assert product["listed_price_cents"] == 9000
    assert product["partner_share_mode"] == "default"
    assert product["partner_share_percent"] is None
    assert product["partner_share_amount_cents"] is None


def test_money_is_sent_as_whole_cents(client, db):
    """Not a float, not a string, and not divided by anything on the way out."""
    add_product(db, 1, quantity_received=1, listed_price_cents=19999)

    product = client.get("/products").json()[0]

    assert product["listed_price_cents"] == 19999
    assert isinstance(product["listed_price_cents"], int)


def test_the_discontinued_flag_is_sent_as_a_boolean(client, db):
    """SQLite stores it as 0 or 1. JSON has a boolean, so the API sends one."""
    add_product(db, 1, quantity_received=1)
    add_product(
        db, 2, quantity_received=1,
        retail_discontinued=1,
        retail_price_cents=0,
        partner_share_mode="custom_amount",
        partner_share_amount_cents=2500,
    )

    products = client.get("/products").json()

    assert products[0]["retail_discontinued"] is False
    assert products[1]["retail_discontinued"] is True


def test_the_partner_cut_comes_from_the_same_function_the_cli_uses(client, db):
    """40 percent of a 100.00 retail price, computed by partner_share_for.

    The API does not work this out for itself, which is the rule the phase
    exists to hold. Asserting the figure matches a direct call to the same
    function is what makes that checkable rather than merely intended.
    """
    add_product(db, 1, quantity_received=1)

    product = client.get("/products").json()[0]
    row = psells.all_products(db)[0]

    assert product["partner_share_cents"] == 4000
    assert product["partner_share_cents"] == psells.partner_share_for(row)


def test_a_fixed_amount_product_reports_that_amount_as_its_cut(client, db):
    add_product(
        db, 1, quantity_received=1,
        retail_discontinued=1,
        retail_price_cents=0,
        partner_share_mode="custom_amount",
        partner_share_amount_cents=2500,
    )

    assert client.get("/products").json()[0]["partner_share_cents"] == 2500


def test_stock_reflects_sales_and_returns(client, db):
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=3)
    add_return(db, 1, item_id=1, quantity=1)

    product = client.get("/products").json()[0]

    assert product["quantity_received"] == 10
    assert product["quantity_sold"] == 3
    assert product["quantity_returned"] == 1
    assert product["quantity_available"] == 6


def test_products_come_back_in_id_order(client, db):
    add_product(db, 2, quantity_received=1, name="Second")
    add_product(db, 1, quantity_received=1, name="First")

    assert [p["name"] for p in client.get("/products").json()] == [
        "First", "Second"
    ]


# Dashboard -------------------------------------------------------------------

def test_the_dashboard_is_all_zeros_on_an_empty_database(client):
    figures = client.get("/dashboard").json()

    assert figures == {
        "total_received": 0,
        "total_sold": 0,
        "total_available": 0,
        "total_returned": 0,
        "total_revenue_cents": 0,
        "total_profit_cents": 0,
        "total_partner_share_cents": 0,
        "total_paid_cents": 0,
        "balance_owing_cents": 0,
    }


def test_the_dashboard_figures(client, db):
    """The same hand-worked scenario the CLI dashboard test uses.

        received   10 + 5                  = 15
        sold       2 + 1                   = 3
        returned   1                       = 1
        available  15 - 3 - 1              = 11
        revenue    2*19999 + 1*5           = 40003
        partner    2*8000  + 1*2           = 16002
        profit     40003 - 16002           = 24001
        paid       10000                   = 10000
        owing      16002 - 10000           = 6002
    """
    add_product(db, 1, quantity_received=10)
    add_product(db, 2, quantity_received=5)
    add_sale(db, 1, item_id=1, quantity=2,
             sale_price_cents=19999, partner_share_cents=8000)
    add_sale(db, 2, item_id=2, quantity=1,
             sale_price_cents=5, partner_share_cents=2)
    add_return(db, 1, item_id=1, quantity=1)
    add_payment(db, 1, amount_cents=10000)

    figures = client.get("/dashboard").json()

    assert figures["total_received"] == 15
    assert figures["total_sold"] == 3
    assert figures["total_available"] == 11
    assert figures["total_returned"] == 1
    assert figures["total_revenue_cents"] == 40003
    assert figures["total_partner_share_cents"] == 16002
    assert figures["total_profit_cents"] == 24001
    assert figures["total_paid_cents"] == 10000
    assert figures["balance_owing_cents"] == 6002


def test_the_dashboard_matches_dashboard_totals_exactly(client, db):
    """The API must not arrive at a different number from the CLI, ever."""
    add_product(db, 1, quantity_received=10)
    add_sale(db, 1, item_id=1, quantity=2,
             sale_price_cents=19999, partner_share_cents=8000)
    add_payment(db, 1, amount_cents=10000)

    figures = client.get("/dashboard").json()
    totals = psells.dashboard_totals(db)

    assert figures["total_revenue_cents"] == totals["total_revenue"]
    assert figures["total_profit_cents"] == totals["total_profit"]
    assert figures["total_partner_share_cents"] == totals["total_partner_share"]
    assert figures["total_paid_cents"] == totals["total_paid"]
    assert figures["balance_owing_cents"] == totals["balance_owing"]


def test_an_overpayment_is_a_negative_balance(client, db):
    add_product(db, 1, quantity_received=1)
    add_sale(db, 1, item_id=1, quantity=1,
             sale_price_cents=2000, partner_share_cents=500)
    add_payment(db, 1, amount_cents=800)

    assert client.get("/dashboard").json()["balance_owing_cents"] == -300


# The generated documentation -------------------------------------------------

def test_the_docs_page_is_served(client):
    """The demo. If this breaks, the thing you show people is broken."""
    assert client.get("/docs").status_code == 200


def test_the_schema_describes_both_endpoints(client):
    schema = client.get("/openapi.json").json()

    assert "/products" in schema["paths"]
    assert "/dashboard" in schema["paths"]
    assert "Product" in schema["components"]["schemas"]


# Recording a sale ------------------------------------------------------------
#
# The first endpoint that writes. Two layers refuse a bad request and they are
# not interchangeable: Pydantic rejects a malformed body with a 422 before the
# endpoint runs at all, and create_sale refuses a well formed request that the
# stock on hand disagrees with. The status codes below say which fired.

def test_a_sale_is_recorded_and_returned(client, db):
    add_product(db, 1, quantity_received=10, name="Jordan 1 Chicago")

    response = client.post("/sales", json={
        "item_id": 1,
        "quantity": 2,
        "sale_price_cents": 8999,
        "date": "2026-09-14",
    })

    assert response.status_code == 201

    sale = response.json()

    assert sale["id"] == 1
    assert sale["item_id"] == 1
    assert sale["quantity"] == 2
    assert sale["sale_price_cents"] == 8999
    assert sale["date"] == "2026-09-14"
    assert sale["partner_share_cents"] == 4000
    assert sale["quantity_available"] == 8


def test_the_sale_is_actually_in_the_database(client, db):
    add_product(db, 1, quantity_received=10)

    client.post("/sales", json={
        "item_id": 1, "quantity": 2, "sale_price_cents": 8999,
    })

    stored = db.execute("SELECT * FROM sales").fetchone()

    assert stored["item_id"] == 1
    assert stored["quantity"] == 2
    assert stored["partner_share_cents"] == 4000


def test_the_date_defaults_to_today(client, db):
    add_product(db, 1, quantity_received=10)

    response = client.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 100,
    })

    assert response.json()["date"] == date.today().isoformat()


def test_a_sale_moves_the_dashboard(client, db):
    """End to end across two endpoints: write through one, read through another."""
    add_product(db, 1, quantity_received=10)

    client.post("/sales", json={
        "item_id": 1, "quantity": 2, "sale_price_cents": 10000,
    })

    figures = client.get("/dashboard").json()

    assert figures["total_sold"] == 2
    assert figures["total_revenue_cents"] == 20000
    assert figures["total_partner_share_cents"] == 8000
    assert figures["total_profit_cents"] == 12000
    assert figures["balance_owing_cents"] == 8000


def test_an_unknown_product_is_a_404(client, db):
    response = client.post("/sales", json={
        "item_id": 99, "quantity": 1, "sale_price_cents": 100,
    })

    assert response.status_code == 404
    assert response.json()["detail"] == "No product with id 99."


def test_selling_more_than_is_available_is_a_409(client, db):
    """The request is well formed. The world disagrees with it."""
    add_product(db, 1, quantity_received=3)

    response = client.post("/sales", json={
        "item_id": 1, "quantity": 4, "sale_price_cents": 100,
    })

    assert response.status_code == 409
    assert "Only 3 available" in response.json()["detail"]
    assert db.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0


def test_a_sold_out_product_is_a_409(client, db):
    add_product(db, 1, quantity_received=2, name="Jordan 1 Chicago")
    add_sale(db, 1, item_id=1, quantity=2)

    response = client.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 100,
    })

    assert response.status_code == 409
    assert "no stock available" in response.json()["detail"]


def test_a_quantity_of_zero_is_a_422(client, db):
    """Refused by the request model, before the endpoint body runs."""
    add_product(db, 1, quantity_received=10)

    response = client.post("/sales", json={
        "item_id": 1, "quantity": 0, "sale_price_cents": 100,
    })

    assert response.status_code == 422
    assert db.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0


def test_a_negative_price_is_a_422(client, db):
    add_product(db, 1, quantity_received=10)

    response = client.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": -1,
    })

    assert response.status_code == 422


def test_a_missing_field_is_a_422_naming_it(client, db):
    add_product(db, 1, quantity_received=10)

    response = client.post("/sales", json={"item_id": 1, "quantity": 1})

    assert response.status_code == 422
    assert any(
        "sale_price_cents" in detail["loc"]
        for detail in response.json()["detail"]
    )


def test_a_date_that_does_not_exist_is_a_422(client, db):
    """There is no 30th of February. Refused as bad input, not as a server error.

    Without a real date type here this would reach the schema's CHECK
    constraint and surface as a 500, which would be a lie: the request was
    wrong, not the server.
    """
    add_product(db, 1, quantity_received=10)

    response = client.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 100,
        "date": "2026-02-30",
    })

    assert response.status_code == 422
    assert db.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 0


def test_the_partner_cut_is_frozen_by_the_endpoint_too(client, db, monkeypatch):
    add_product(db, 1, quantity_received=10)

    first = client.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 8999,
    }).json()

    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 10.0)

    second = client.post("/sales", json={
        "item_id": 1, "quantity": 1, "sale_price_cents": 8999,
    }).json()

    assert first["partner_share_cents"] == 4000
    assert second["partner_share_cents"] == 1000
    assert client.get("/dashboard").json()["total_partner_share_cents"] == 5000


def test_the_schema_documents_the_sales_endpoint(client):
    schema = client.get("/openapi.json").json()

    assert "post" in schema["paths"]["/sales"]
    assert "NewSale" in schema["components"]["schemas"]
