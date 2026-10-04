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

Every page needs a live session, except the login page. The rules about
passwords and sessions are in auth.py; this file only carries the cookie.
"""

import datetime
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import auth
import psells
from dependencies import (
    SESSION_COOKIE, Connection, Session, check_form_token,
    require_page_session)


# Every page is on router, which refuses a request without a live session, or
# a write without the session's form token, before the route runs. The login
# page, which has to be reachable without either, is on public, and nothing
# else is.
router = APIRouter(include_in_schema=False,
                   dependencies=[Depends(require_page_session),
                                 Depends(check_form_token)])
public = APIRouter(include_in_schema=False)

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
def inventory_page(request: Request, connection: Connection, q: str = "",
                   added: str = "", edited: str = "", sold: str = "",
                   returned: str = "", paid: str = ""):
    """Every product with a unit available, in one table, under the dashboard.

    The screen that replaces the spreadsheet. The nine figures above the table
    are dashboard_totals, the function the command line's dashboard and the
    API's /dashboard call, handed to the template as they come back. They
    describe every product, in stock or not. Which products are in stock is
    decided by in_stock_products, and the rest are on out_of_stock_page.

    q is the search box, arriving as ?q= in the URL. A term narrows the table
    through find_items_by_name_or_category, the command line's own search, so
    the two cannot disagree about what matches. It searches the products in
    stock only, the ones the table can show. The term is stripped, as the
    command line strips what it reads. No term, or only spaces, means no search
    and the whole inventory, which is said here rather than left to the fact
    that an empty string is found inside every string.

    added, edited, sold and returned are the id of a product just added,
    changed, sold or returned, and paid the id of a payment just recorded,
    carried here by the redirect after a form. Each is read as text and matched against
    the ids that exist, so a typed ?added=abc or an id that does not exist
    shows nothing rather than an error or a false message. They are looked up
    among every product, not only those in stock, so a sale of the last unit,
    or an edit made from the out-of-stock page, is still confirmed. When the
    product named is not in stock, the page says so and links to where it is.

    The dashboard is never narrowed by a search. It describes the business,
    and totals for whichever rows happen to be showing would mean adding them
    up here, outside psells.

    The partner cut is not a column of products_view, so it is worked out here
    for each product by partner_share_for, the same function the API's
    to_product and the command line's print_product call. The template is
    handed the figure and never works it out.
    """
    term = q.strip()
    everything = psells.all_products(connection)
    in_stock = psells.in_stock_products(connection)
    products = in_stock

    if term:
        products = psells.find_items_by_name_or_category(in_stock, term)

    def named(product_id):
        return next((product for product in everything
                     if str(product["id"]) == product_id), None)

    confirmed = [named(added), named(edited), named(sold), named(returned)]
    in_stock_ids = {product["id"] for product in in_stock}
    now_out_of_stock = next(
        (product for product in confirmed
         if product is not None and product["id"] not in in_stock_ids),
        None,
    )

    payment_recorded = next(
        (payment for payment in psells.all_payments(connection)
         if str(payment["id"]) == paid),
        None,
    ) if paid else None

    inventory = [
        (product, psells.partner_share_for(product))
        for product in products
    ]

    return templates.TemplateResponse(
        request,
        "inventory.html",
        {
            "totals": psells.dashboard_totals(connection),
            "inventory": inventory,
            "q": term,
            "added": confirmed[0],
            "edited": confirmed[1],
            "sold": confirmed[2],
            "returned": confirmed[3],
            "now_out_of_stock": now_out_of_stock,
            "paid": payment_recorded,
        },
    )


@router.get("/out-of-stock", response_class=HTMLResponse)
def out_of_stock_page(request: Request, connection: Connection, q: str = ""):
    """Every product with no unit available, and why.

    The other half of the inventory: out_of_stock_products and
    in_stock_products between them list every product exactly once. The reason
    beside each, "Sold out", "Returned" or a mix such as "2 sold, 1 returned
    of 3", is out_of_stock_reason's, worked out in psells and only shown here.

    q searches these products alone, with the inventory's search function and
    the same stripping. Rows offer Edit only. Delete stays one step further
    away, on the edit page, as it is from the inventory.
    """
    term = q.strip()
    products = psells.out_of_stock_products(connection)

    if term:
        products = psells.find_items_by_name_or_category(products, term)

    rows = [
        (product, psells.partner_share_for(product),
         psells.out_of_stock_reason(product))
        for product in products
    ]

    return templates.TemplateResponse(
        request,
        "out_of_stock.html",
        {"rows": rows, "q": term},
    )


# Adding a product ------------------------------------------------------------

class ProductForm(BaseModel):
    """The add form's fields, every one text, every one optional.

    Optional because FastAPI treats a blank form field as not sent, and a
    required one would answer a blank with a JSON error rather than the form.
    PSells decides what blank means, in read_product_text. Text because money
    must reach parse_money as typed: a float here would be converted by the
    framework before any PSells code ran.
    """

    category: str = ""
    name: str = ""
    quantity_received: str = ""
    retail_discontinued: str = ""
    retail_price: str = ""
    listed_price: str = ""
    condition: str = ""
    notes: str = ""
    partner_share_mode: str = ""
    partner_share_percent: str = ""
    partner_share_amount: str = ""


BLANK_PRODUCT = ProductForm(partner_share_mode="default").model_dump()


def product_form(request, values, problems, status_code=200, product=None):
    """The product form, for adding or for editing one product.

    Empty, filled from the stored product, or as it was typed, with a sentence
    per problem. One template for adding and editing and for both the first
    showing and a refusal, so there is one copy of the form.
    """
    if product is None:
        action = request.url_for("add_product_submit")
    else:
        action = request.url_for("edit_product_submit",
                                 product_id=product["id"])

    return templates.TemplateResponse(
        request,
        "product_form.html",
        {"values": values, "errors": problems, "product": product,
         "action": action},
        status_code=status_code,
    )


def not_found(request, product_id):
    return templates.TemplateResponse(
        request, "not_found.html", {"product_id": product_id},
        status_code=404,
    )


@router.get("/products/new", response_class=HTMLResponse)
def add_product_page(request: Request):
    return product_form(request, BLANK_PRODUCT, {})


@router.post("/products/new", response_class=HTMLResponse)
def add_product_submit(request: Request, connection: Connection,
                       form: Annotated[ProductForm, Form()]):
    """Add the product, or show the form again with every problem.

    Success redirects with 303, so the page left on screen came from a GET and
    refreshing it cannot add the product twice. RedirectResponse defaults to
    307, which would re-send the post, so the code is always written out.

    A refusal writes nothing and answers 422 with everything as it was typed,
    so one mistake costs one correction.
    """
    fields = form.model_dump()

    try:
        product_id = psells.create_product_from_text(connection, fields)
    except psells.ProductError as refused:
        return product_form(request, fields, refused.problems, status_code=422)

    return RedirectResponse(
        request.url_for("inventory_page").include_query_params(added=product_id),
        status_code=303,
    )


# Editing a product -----------------------------------------------------------
#
# {product_id:int} in the path means a URL whose id is not a whole number does
# not match this route at all and is a plain 404, rather than matching it and
# failing validation with a JSON 422.

def find_product(connection, product_id):
    """The product with this id from products_view, or None."""
    return next((product for product in psells.all_products(connection)
                 if product["id"] == product_id), None)


@router.get("/products/{product_id:int}/edit", response_class=HTMLResponse)
def edit_product_page(request: Request, connection: Connection,
                      product_id: int):
    """The product form, filled with the product as it is stored.

    The text comes from product_form_text, which reads back as exactly the
    stored values, so saving without touching anything changes nothing.
    """
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    return product_form(request, psells.product_form_text(product), {},
                        product=product)


@router.post("/products/{product_id:int}/edit", response_class=HTMLResponse)
def edit_product_submit(request: Request, connection: Connection,
                        product_id: int,
                        form: Annotated[ProductForm, Form()]):
    """Save every field, or show the form again with every problem.

    A field that arrives empty was emptied on purpose, because the form opened
    filled in: emptied notes are cleared, and an emptied required field is
    refused. That is the opposite of the command line, where Enter keeps the
    current value, and it was decided that way. Success redirects with 303,
    as adding does.
    """
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    fields = form.model_dump()

    try:
        psells.update_product_from_text(connection, product_id, fields)
    except psells.ProductError as refused:
        return product_form(request, fields, refused.problems,
                            status_code=422, product=product)

    return RedirectResponse(
        request.url_for("inventory_page").include_query_params(
            edited=product_id),
        status_code=303,
    )


# Recording a sale ------------------------------------------------------------

class SaleForm(BaseModel):
    """The sale form's fields: text, optional, for the reasons ProductForm
    gives. The date is text too, even from a date picker, and is read by
    read_sale_text as the command line reads it."""

    quantity: str = ""
    sale_price: str = ""
    date: str = ""


def sale_form(request, product, values, problems, status_code=200):
    """The sale form for one product, with the partner cut it would freeze.

    The cut is partner_share_for, the same call create_sale makes when the sale
    is recorded, so the figure on the page is the figure that will be frozen.
    """
    return templates.TemplateResponse(
        request,
        "sale_form.html",
        {
            "product": product,
            "partner_cut": psells.partner_share_for(product),
            "values": values,
            "errors": problems,
        },
        status_code=status_code,
    )


@router.get("/products/{product_id:int}/sell", response_class=HTMLResponse)
def sell_product_page(request: Request, connection: Connection,
                      product_id: int):
    """The sale form, starting at one unit, dated today, price blank.

    The price is left blank on purpose: the command line has no default price,
    so the page does not invent one. The listed price is shown beside it.
    """
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    values = {"quantity": "1", "sale_price": "",
              "date": datetime.date.today().isoformat()}

    return sale_form(request, product, values, {})


@router.post("/products/{product_id:int}/sell", response_class=HTMLResponse)
def sell_product_submit(request: Request, connection: Connection,
                        product_id: int, form: Annotated[SaleForm, Form()]):
    """Record the sale, or show the form again saying why not.

    422 when what was typed is wrong in itself, 409 when it was fine and the
    stock disagrees, the same split the API makes. Success redirects with 303,
    which matters most here: a sale repeated by a refresh is a second sale,
    with a second partner cut frozen onto it.
    """
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    fields = form.model_dump()

    try:
        psells.create_sale_from_text(connection, product_id, fields)
    except psells.SaleInputError as refused:
        return sale_form(request, product, fields, refused.problems,
                         status_code=422)
    except psells.ProductNotFound:
        return not_found(request, product_id)
    except psells.SaleError as refused:
        return sale_form(request, product, fields,
                         {"quantity": str(refused)}, status_code=409)

    return RedirectResponse(
        request.url_for("inventory_page").include_query_params(
            sold=product_id),
        status_code=303,
    )


# Recording a return ----------------------------------------------------------

class ReturnForm(BaseModel):
    """The return form's fields, text and optional, as for a sale."""

    quantity: str = ""
    date: str = ""
    notes: str = ""


def return_form(request, product, values, problems, status_code=200):
    return templates.TemplateResponse(
        request,
        "return_form.html",
        {"product": product, "values": values, "errors": problems},
        status_code=status_code,
    )


@router.get("/products/{product_id:int}/return", response_class=HTMLResponse)
def return_product_page(request: Request, connection: Connection,
                        product_id: int):
    """The return form, starting at one unit, dated today, no notes."""
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    values = {"quantity": "1", "date": datetime.date.today().isoformat(),
              "notes": ""}

    return return_form(request, product, values, {})


@router.post("/products/{product_id:int}/return", response_class=HTMLResponse)
def return_product_submit(request: Request, connection: Connection,
                          product_id: int,
                          form: Annotated[ReturnForm, Form()]):
    """Record the return, or show the form again saying why not.

    422 for text wrong in itself, 409 when the stock disagrees, 303 on success,
    as for a sale.
    """
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    fields = form.model_dump()

    try:
        psells.create_return_from_text(connection, product_id, fields)
    except psells.ReturnInputError as refused:
        return return_form(request, product, fields, refused.problems,
                           status_code=422)
    except psells.ProductNotFound:
        return not_found(request, product_id)
    except psells.ReturnError as refused:
        return return_form(request, product, fields,
                           {"quantity": str(refused)}, status_code=409)

    return RedirectResponse(
        request.url_for("inventory_page").include_query_params(
            returned=product_id),
        status_code=303,
    )


# Recording a payment to the partner ------------------------------------------

class PaymentForm(BaseModel):
    """The payment form's fields, text and optional, as for the others."""

    amount: str = ""
    date: str = ""
    notes: str = ""


def payment_form(request, connection, values, problems, status_code=200):
    """The payment form, under what is owed. The three figures are
    dashboard_totals', the same the dashboard panel shows."""
    return templates.TemplateResponse(
        request,
        "payment_form.html",
        {"totals": psells.dashboard_totals(connection), "values": values,
         "errors": problems},
        status_code=status_code,
    )


@router.get("/payments/new", response_class=HTMLResponse)
def add_payment_page(request: Request, connection: Connection):
    """Dated today, amount blank: there is no default amount to pay."""
    values = {"amount": "", "date": datetime.date.today().isoformat(),
              "notes": ""}

    return payment_form(request, connection, values, {})


@router.post("/payments/new", response_class=HTMLResponse)
def add_payment_submit(request: Request, connection: Connection,
                       form: Annotated[PaymentForm, Form()]):
    """Record the payment, or show the form again with every problem.

    Success redirects with 303 carrying the new payment's id. A refresh that
    repeated this post would pay the partner twice on paper, which is the one
    mistake here that would change the balance owing.
    """
    fields = form.model_dump()

    try:
        payment_id = psells.create_payment_from_text(connection, fields)
    except psells.PaymentInputError as refused:
        return payment_form(request, connection, fields, refused.problems,
                            status_code=422)

    return RedirectResponse(
        request.url_for("inventory_page").include_query_params(
            paid=payment_id),
        status_code=303,
    )


# Deleting a product ----------------------------------------------------------

def delete_page(request, product, blocker, status_code=200):
    """The confirmation page. It is the confirmation: the delete happens only
    when its form is posted. A product with history gets the reason instead
    of a button, so nobody confirms a delete that is then refused."""
    return templates.TemplateResponse(
        request,
        "delete_confirm.html",
        {"product": product, "blocker": blocker},
        status_code=status_code,
    )


@router.get("/products/{product_id:int}/delete", response_class=HTMLResponse)
def delete_product_page(request: Request, connection: Connection,
                        product_id: int):
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    return delete_page(request, product,
                       psells.deletion_blocker(connection, product_id))


@router.post("/products/{product_id:int}/delete", response_class=HTMLResponse)
def delete_product_submit(request: Request, connection: Connection,
                          product_id: int):
    """Delete, or show why not with a 409.

    Success redirects with 303 to the inventory, with no message: the product
    no longer exists to be named, and a message built from an id in the address
    bar could not be checked against anything. The row is simply gone.
    """
    product = find_product(connection, product_id)

    if product is None:
        return not_found(request, product_id)

    try:
        psells.delete_product(connection, product_id)
    except psells.ProductNotFound:
        return not_found(request, product_id)
    except psells.DeleteRefused as refused:
        return delete_page(request, product, str(refused), status_code=409)

    return RedirectResponse(request.url_for("inventory_page"),
                            status_code=303)


# Logging in and out ------------------------------------------------------------

def login_form(request, username="", problem="", status_code=200):
    return templates.TemplateResponse(
        request, "login.html",
        {"values": {"username": username, "password": ""},
         "errors": {}, "problem": problem},
        status_code=status_code,
    )


@public.get("/login", response_class=HTMLResponse)
def login_page(request: Request, session: Session):
    """The login form, or the inventory for someone already logged in."""
    if session is not None:
        return RedirectResponse(request.url_for("inventory_page"),
                                status_code=303)
    return login_form(request)


@public.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, connection: Connection,
                 username: Annotated[str, Form()] = "",
                 password: Annotated[str, Form()] = ""):
    """Log in and go to the inventory, or show the form again with a 401.

    A wrong password and an unknown username get the same sentence, so the
    page does not say which usernames exist. The username comes back as it
    was typed; the password never does.

    Any session the browser already had is ended first, and the new one gets
    new values, so a cookie someone planted before the login is worthless
    after it.

    The cookie lasts as long as the longest a session can, so the browser
    forgets it no later than the server would. HttpOnly keeps it from any
    script; SameSite=Lax keeps it off another site's form posts.
    """
    user_id = auth.check_login(connection, username, password)

    if user_id is None:
        return login_form(request, username,
                          "The username or password is wrong.",
                          status_code=401)

    auth.end_session(connection, request.cookies.get(SESSION_COOKIE))
    cookie_value, _ = auth.start_session(connection, user_id, auth.now())

    response = RedirectResponse(request.url_for("inventory_page"),
                                status_code=303)
    response.set_cookie(
        SESSION_COOKIE, cookie_value,
        max_age=int(auth.ABSOLUTE_LIMIT.total_seconds()),
        path="/", secure=True, httponly=True, samesite="lax",
    )
    return response


@router.post("/logout")
def logout(request: Request, connection: Connection):
    """End this session and go back to the login page.

    POST rather than a link, so that nothing another page can load, an image
    or a link followed in the background, can log anyone out. The cookie is
    deleted with the same attributes it was set with, or a browser keeps the
    __Host- one.
    """
    auth.end_session(connection, request.cookies.get(SESSION_COOKIE))

    response = RedirectResponse(request.url_for("login_page"),
                                status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True,
                           httponly=True, samesite="lax")
    return response
