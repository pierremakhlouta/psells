"""The HTTP API for PSells.

A second front door onto the same application, not a second application. Every
figure served here is produced by the functions psells.py already uses: stock
comes from products_view, the partner cut from partner_share_for, the dashboard
from dashboard_totals, and a sale is recorded by create_sale. Nothing in this
file works out a business figure for itself, and nothing in it should.

The same application serves the web pages in web.py, included at the bottom
of this file, so one uvicorn command runs both. They are a separate file
because they return HTML for a person rather than JSON for a program, and they
do not appear in the generated documentation at /docs.

Money crosses the wire as a whole number of cents, never as dollars and never
as a formatted string. That matches how it is stored, keeps every value exact,
and leaves formatting to whatever is showing it to a person.

It runs in the Compose stack, which sets the two things it reads from its
environment: PSELLS_DATABASE_URL, the PostgreSQL database, and PSELLS_CONFIG,
the configuration file.

    docker compose up --build -d --wait

The database has no default, so running it anywhere else means naming one, and
pointing it at a copy rather than the real records is always a deliberate act:

    PSELLS_DATABASE_URL=postgresql://... PSELLS_CONFIG=/path/to/config.json uvicorn api:app
"""

import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

import cross_site
import psells
import web
from dependencies import Connection


app = FastAPI(
    title="PSells API",
    description=(
        "Read the inventory and the dashboard, and record a sale. "
        "All money is in whole cents."
    ),
    version="0.1.0",
    # No /docs and no /redoc. FastAPI builds both from JavaScript loaded from
    # a CDN and pinned only to a major version, and it would run on the same
    # origin as the forms, which the cross-site check trusts. The strict
    # Content-Security-Policy nginx sends would refuse it anyway. The same
    # description of the API is served as plain JSON at /openapi.json.
    docs_url=None,
    redoc_url=None,
)


# Cross-site writes -------------------------------------------------------------
#
# Checked once, here, for every route the application has or will have, so a new
# form cannot be added without it. The reasoning is in cross_site.py.
#
# This is async where every endpoint is a plain def, and that is not a
# contradiction: middleware wraps every request and must be async, and nothing
# here waits on the database. It reads two headers and either answers at once or
# hands the request on.

@app.middleware("http")
async def refuse_cross_site_writes(request, call_next):
    reason = cross_site.refusal(
        request.method,
        request.headers,
        request.url.scheme,
        request.headers.get("host", ""),
    )

    if reason is not None:
        return PlainTextResponse(
            f"Refused: a write from another site. {reason}", status_code=403
        )

    return await call_next(request)


# What the API sends back -----------------------------------------------------
#
# These say what a caller receives, rather than letting whatever columns
# products_view happens to have become the published contract by accident.
# Renaming a column in schema.sql now breaks this file loudly instead of
# changing what every client receives silently.

class Product(BaseModel):
    id: int
    category: str
    name: str
    condition: str
    notes: str

    quantity_received: int = Field(description="Units originally taken in.")
    quantity_sold: int
    quantity_returned: int
    quantity_available: int = Field(
        description="received minus sold minus returned."
    )

    retail_price_cents: int
    listed_price_cents: int
    retail_discontinued: bool = Field(
        description=(
            "Discontinued at retail. The product is still held, still listed "
            "and still sellable."
        )
    )

    partner_share_mode: str
    partner_share_percent: float | None
    partner_share_amount_cents: int | None
    partner_share_cents: int = Field(
        description="The partner's cut for one unit, as it stands today."
    )


class NewSale(BaseModel):
    """One sale, as a caller sends it.

    Every bound here is checked before the endpoint runs, so a malformed request
    is answered with a 422 naming the field rather than reaching the database.
    create_sale checks the same things again, because it is also called from the
    CLI and must not depend on who its caller happens to be.

    date is a real date, so 2026-02-30 is refused here rather than by a CHECK
    constraint. Leave it out and today is used, the same as pressing Enter at
    the CLI's date prompt.
    """

    item_id: int
    quantity: int = Field(ge=1)
    sale_price_cents: int = Field(ge=0, description="Price per unit, in cents.")
    date: datetime.date | None = Field(
        default=None, description="Defaults to today."
    )


class Sale(BaseModel):
    id: int
    date: datetime.date
    item_id: int
    quantity: int
    sale_price_cents: int
    partner_share_cents: int = Field(
        description=(
            "The partner's cut per unit, frozen onto this sale. Changing the "
            "default rate later does not alter it."
        )
    )
    quantity_available: int = Field(
        description="The product's remaining stock after this sale."
    )


class Dashboard(BaseModel):
    total_received: int
    total_sold: int
    total_available: int
    total_returned: int

    total_revenue_cents: int
    total_profit_cents: int
    total_partner_share_cents: int
    total_paid_cents: int
    balance_owing_cents: int = Field(
        description="Partner share earned minus paid. Negative if overpaid."
    )


def to_product(row):
    """One row of products_view as the API describes a product.

    partner_share_cents is not in the row. It is worked out by the same
    partner_share_for the CLI calls, so the figure here and the Partner Cut the
    CLI prints cannot disagree.
    """
    return Product(
        **dict(row),
        partner_share_cents=psells.partner_share_for(row),
    )


# Endpoints -------------------------------------------------------------------

@app.get("/products", response_model=list[Product], tags=["products"])
def read_products(connection: Connection):
    """Every product, in id order, with its derived quantities."""
    return [to_product(row) for row in psells.all_products(connection)]


@app.get("/dashboard", response_model=Dashboard, tags=["dashboard"])
def read_dashboard(connection: Connection):
    """The nine dashboard figures. Quantities are counts, money is cents."""
    totals = psells.dashboard_totals(connection)

    return Dashboard(
        total_received=totals["total_received"],
        total_sold=totals["total_sold"],
        total_available=totals["total_available"],
        total_returned=totals["total_returned"],
        total_revenue_cents=totals["total_revenue"],
        total_profit_cents=totals["total_profit"],
        total_partner_share_cents=totals["total_partner_share"],
        total_paid_cents=totals["total_paid"],
        balance_owing_cents=totals["balance_owing"],
    )


@app.post(
    "/sales",
    response_model=Sale,
    status_code=201,
    tags=["sales"],
    responses={
        404: {"description": "No product with that id."},
        409: {"description": "The sale conflicts with the stock on hand."},
    },
)
def record_sale(new_sale: NewSale, connection: Connection):
    """Record one sale and return it, including the partner cut it froze.

    The work is create_sale, which is what the CLI calls once its prompts have
    collected the same five values. This function translates a refusal into a
    status code and reads the stored row back; it decides nothing.

    404 and 409 are different on purpose. A missing product means correct the
    id. A stock conflict means the request was well formed and the world
    disagrees with it, so correct the quantity.
    """
    sale_date = (new_sale.date or datetime.date.today()).isoformat()

    try:
        psells.create_sale(
            connection,
            new_sale.item_id,
            new_sale.quantity,
            new_sale.sale_price_cents,
            sale_date,
        )
    except psells.ProductNotFound as error:
        raise HTTPException(status_code=404, detail=str(error))
    except psells.SaleError as error:
        raise HTTPException(status_code=409, detail=str(error))

    # lastval() is the id the sales sequence last handed to this connection,
    # and this request has its own connection, so it cannot pick up a row
    # inserted by anybody else. create_sale's insert is the last thing on this
    # connection to draw from any sequence.
    stored = connection.execute(
        "SELECT * FROM sales WHERE id = lastval()"
    ).fetchone()

    return Sale(
        **dict(stored),
        quantity_available=connection.execute(
            "SELECT quantity_available FROM products_view WHERE id = %s",
            (new_sale.item_id,)
        ).fetchone()["quantity_available"],
    )


# The web pages ---------------------------------------------------------------
#
# Included rather than written here. web.py takes its connection from
# dependencies.py rather than from this file, which is what lets this file
# import web.py without web.py having to import this one back.

app.include_router(web.router)
