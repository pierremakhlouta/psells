"""The HTTP API for PSells.

A second front door onto the same application, not a second application. Every
figure served here is produced by the functions psells.py already uses: stock
comes from products_view, the partner cut from partner_share_for, the dashboard
from dashboard_totals, and a sale is recorded by create_sale. Nothing in this
file works out a business figure for itself, and nothing in it should.

Money crosses the wire as a whole number of cents, never as dollars and never
as a formatted string. That matches how it is stored, keeps every value exact,
and leaves formatting to whatever is showing it to a person.

Run it with:

    uvicorn api:app --reload

from the project folder, because psells.py opens data/psells.db and
data/config.json by paths relative to the working directory.
"""

import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

import psells


app = FastAPI(
    title="PSells API",
    description=(
        "Read the inventory and the dashboard, and record a sale. "
        "All money is in whole cents."
    ),
    version="0.1.0",
)


# Connections -----------------------------------------------------------------

def get_connection():
    """One connection per request, closed when the request finishes.

    A connection cannot be shared between the two. Python's sqlite3 refuses to
    use a connection from any thread other than the one that opened it, and
    every endpoint here is a plain def, which FastAPI runs in a thread pool. A
    module-level connection would work in testing and fail under a second
    caller.

    psells.connect is used rather than sqlite3.connect directly, so the foreign
    key pragma and the row factory are applied exactly once, in one place.
    """
    connection = psells.connect(check_same_thread=False)

    try:
        yield connection
    finally:
        connection.close()


Connection = Annotated[sqlite3.Connection, Depends(get_connection)]


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
