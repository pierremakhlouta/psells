"""The web pages for PSells.

Server-rendered HTML on top of the same functions the command line and the API
already call. A third front door onto one application, not a third application.

Three rules hold this file to that. They are recorded in DECISIONS.md, and
tests/test_web.py enforces them wherever a test can:

1. A route that renders a page calls psells functions and nothing else. No
   arithmetic on money, stock or partner share happens here.
2. Wherever a page shows a figure the API also serves, a test asserts that the
   two agree.
3. Templates, and the filters they use, format. They never compute.

Every route is a plain def, for the reason given in dependencies.py. None of
them appears in the API's generated documentation, because they return HTML
for a person rather than JSON for a program.
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import psells
from dependencies import Connection


router = APIRouter(include_in_schema=False)

# Beside this file, not beside the shell. A bare "templates" would be looked up
# from whatever directory uvicorn happened to be started in, which is the same
# failure the database and config paths had until Phase 03.
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "templates")
)

# The one money formatter, under a name a template can use. This is not a
# second implementation: it is the function the command line prints with.
templates.env.filters["money"] = psells.format_cents


@router.get("/", response_class=HTMLResponse)
def inventory_page(request: Request, connection: Connection):
    """Every product in one table, the screen that replaces the spreadsheet.

    The partner cut is not a column of products_view, so it is worked out here
    for each product by partner_share_for, the same function the API's
    to_product and the command line's print_product call. The template is
    handed the figure and never works it out.
    """
    inventory = [
        (product, psells.partner_share_for(product))
        for product in psells.all_products(connection)
    ]

    return templates.TemplateResponse(
        request, "inventory.html", {"inventory": inventory}
    )
