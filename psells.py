import os
import json
import math
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import psycopg
from psycopg.rows import dict_row


# Where the data lives.
#
# The configuration file defaults to the data folder beside this file rather
# than beside the shell that started the process. Relative paths cost this
# project three separate surprises: the CI tests failed four frames below the
# line under test because a checkout has no data folder, the API served nothing
# unless uvicorn happened to be started from the right directory, and a sandbox
# worked only as a side effect of changing directory. PSELLS_CONFIG overrides
# it, which is how the container is given its one mounted file.
#
# The database is a PostgreSQL server named by PSELLS_DATABASE_URL, and has no
# default: the only place the application runs against the real one is inside
# the Compose stack, which sets it. A default would have to name a host and a
# password, and a wrong guess connecting somewhere is worse than a sentence.
#
# Both are read once, when this module is imported, because a process does not
# change its mind about which database it is using halfway through.

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def path_from_environment(variable, *parts):
    """An override from the environment, or a path beside this file.

    An empty variable counts as unset. Exporting PSELLS_DB= and meaning "use the
    default" is a reasonable reading, and treating it as a path to the file ""
    is not.
    """
    return os.environ.get(variable) or os.path.join(PROJECT_DIR, *parts)


CONFIG_FILE = path_from_environment("PSELLS_CONFIG", "data", "config.json")
DATABASE_URL = os.environ.get("PSELLS_DATABASE_URL", "")


class DatabaseUnavailable(RuntimeError):
    """The database cannot be reached, with a sentence saying what to do."""


def connect():
    """Open the database and hand back a connection that is ready to use.

    autocommit is on, and that is not a shortcut. With it off, psycopg opens a
    transaction at the first statement and keeps it open until something
    commits. Every write here is wrapped in connection.transaction(), and inside
    a transaction that is already open that block is only a savepoint: the
    write would look done, be visible to this connection, and vanish when the
    connection closed. With autocommit on, a read is its own statement and each
    transaction() block is a real transaction that commits when it ends.

    dict_row makes a row readable by column name, so product["name"] keeps
    working, as sqlite3.Row did. Unlike sqlite3.Row it cannot be read by
    position, so a query read by position names its column instead.

    Raises DatabaseUnavailable with a sentence when PSELLS_DATABASE_URL is not
    set or the server does not answer.
    """
    if not DATABASE_URL:
        raise DatabaseUnavailable(
            "PSELLS_DATABASE_URL is not set. PSells runs against the database "
            "in its Compose stack: docker compose exec app python psells.py"
        )

    try:
        return psycopg.connect(
            DATABASE_URL, autocommit=True, row_factory=dict_row)
    except psycopg.OperationalError as error:
        raise DatabaseUnavailable(
            f"Could not reach the database: {error}".strip()
        ) from error


def all_products(connection):
    """Every product, with its derived quantities, in id order.

    Always read through products_view rather than the products table, because
    quantity_sold, quantity_returned and quantity_available only exist there.

    ORDER BY is not decoration. Without it the database makes no promise about
    the order rows come back in. It happens to match id order today, which is
    exactly the kind of accident that changes silently later.
    """
    return connection.execute(
        "SELECT * FROM products_view ORDER BY id"
    ).fetchall()


def format_cents(cents, *, symbol=True):
    """Format a whole number of cents as money, for display only.

    Thousands are grouped with commas, $12,345.67, because a figure has to be
    read at a glance and not counted.

    symbol=False leaves out the dollar sign and the commas, giving text
    parse_money reads back as the same number of cents. That is what an edit
    form puts in a box to be typed over, so the two conversions stay the only
    two.

    The dollar sign is part of what comes back, so a negative figure reads
    -$3.00 and not $-3.00. It used to be left to the caller, and every caller
    printed a "$" in front of whatever this returned, minus sign included. One
    function owning the whole rendering is what stops that coming back the next
    time somebody adds a call site.

    Deliberately integer arithmetic. Dividing by 100 would turn money back into
    a float at the last moment, which is the one thing the storage decision was
    meant to stop. Handles a negative figure, which balance owing can be.
    """
    sign = "-" if cents < 0 else ""
    cents = abs(cents)

    if symbol:
        return f"{sign}${cents // 100:,}.{cents % 100:02d}"

    return f"{sign}{cents // 100}.{cents % 100:02d}"


def parse_money(text):
    """Turn a typed dollar figure into a whole number of cents.

    Raises ValueError if the text is not a number, or if it carries more than
    two decimal places. A tenth of a cent is not an amount of money, and quietly
    rounding it away would store a different figure from the one that was typed.
    """
    try:
        amount = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError("not a number")

    if not amount.is_finite():
        raise ValueError("not a finite number")

    if amount != amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
        raise ValueError("more than two decimal places")

    return int(amount * 100)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"{CONFIG_FILE} not found. "
            f"Copy sample_data/config.json into data/ and set your own values."
        )

    with open(CONFIG_FILE) as f:
        return json.load(f)


def ask_text(prompt):
    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("Input cannot be blank. Please try again.")


def ask_optional_text(prompt):
    return input(prompt).strip()


def ask_int(prompt, min_value=None, max_value=None):
    while True:
        try:
            value = int(input(prompt))

            if min_value is not None and value < min_value:
                print(f"Value must be at least {min_value}.")
                continue

            if max_value is not None and value > max_value:
                print(f"Value must be at most {max_value}.")
                continue

            return value

        except ValueError:
            print("Please enter a valid whole number.")


def ask_float(prompt, min_value=None, max_value=None):
    while True:
        try:
            value = float(input(prompt))

            # float() reads "nan" and "inf" as numbers, and neither is an
            # amount of anything. nan would also pass every range check below,
            # because it compares false with every number. Refused the same way
            # as text that is not a number at all.
            if not math.isfinite(value):
                raise ValueError(f"{value} is not a finite number")

            if min_value is not None and value < min_value:
                print(f"Value must be at least {min_value}.")
                continue

            if max_value is not None and value > max_value:
                print(f"Value must be at most {max_value}.")
                continue

            return value

        except ValueError:
            print("Please enter a valid number.")


def ask_money(prompt, min_cents=None, max_cents=None):
    while True:
        try:
            cents = parse_money(input(prompt))
        except ValueError:
            print("Please enter an amount in dollars, for example 12.50.")
            continue

        if min_cents is not None and cents < min_cents:
            print(f"Value must be at least {format_cents(min_cents)}.")
            continue

        if max_cents is not None and cents > max_cents:
            print(f"Value must be at most {format_cents(max_cents)}.")
            continue

        return cents


def ask_choice(prompt, options):
    while True:
        value = input(prompt).strip().lower()

        if value in options:
            return value

        print("Invalid choice. Please try again.")


def ask_date(prompt):
    while True:
        text = input(
            f"{prompt} (YYYY-MM-DD, blank for today): "
        ).strip()

        if text == "":
            return date.today().isoformat()

        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
            return parsed.strftime("%Y-%m-%d")

        except ValueError:
            print("Please enter a valid date in YYYY-MM-DD format.")


def ask_edit_text(prompt, current):
    value = input(f"{prompt} [{current}]: ").strip()

    if value == "":
        return current

    return value


def ask_edit_number(
    prompt,
    current,
    value_type,
    min_value=None,
    max_value=None
):
    while True:
        value = input(f"{prompt} [{current}]: ").strip()

        if value == "":
            return current

        try:
            value = value_type(value)

            if min_value is not None and value < min_value:
                print(f"Value must be at least {min_value}.")
                continue

            if max_value is not None and value > max_value:
                print(f"Value must be at most {max_value}.")
                continue

            return value

        except ValueError:
            if value_type is int:
                print("Please enter a valid whole number.")
            else:
                print("Please enter a valid number.")


def ask_edit_money(prompt, current_cents, min_cents=None, max_cents=None):
    while True:
        text = input(f"{prompt} [{format_cents(current_cents)}]: ").strip()

        if text == "":
            return current_cents

        try:
            cents = parse_money(text)
        except ValueError:
            print("Please enter an amount in dollars, for example 12.50.")
            continue

        if min_cents is not None and cents < min_cents:
            print(f"Value must be at least {format_cents(min_cents)}.")
            continue

        if max_cents is not None and cents > max_cents:
            print(f"Value must be at most {format_cents(max_cents)}.")
            continue

        return cents


def ask_edit_choice(prompt, current, options):
    while True:
        value = input(
            f"{prompt} [{current}]: "
        ).strip().lower()

        if value == "":
            return current

        if value in options:
            return value

        print("Invalid choice. Please try again.")


def ask_partner_share(retail_discontinued):
    """Ask how the partner's cut is set for one product.

    Returns three values, (mode, percent, amount_cents), with exactly one of the
    last two filled in and the other None. That is the shape the products table
    requires, and the matrix constraint refuses anything else.

    A product discontinued at retail has no retail price to take a percentage
    of, so the fixed per-unit amount is the only mode offered rather than being
    offered and then rejected.

    This replaces four near-identical copies of the same block that used to sit
    inside add and edit.
    """
    if retail_discontinued:
        amount_cents = ask_money(
            "Partner share per unit ($): ",
            min_cents=0
        )

        return "custom_amount", None, amount_cents

    mode = ask_choice(
        "Partner-share mode "
        "(default/custom_percent/custom_amount): ",
        ["default", "custom_percent", "custom_amount"]
    )

    if mode == "custom_percent":
        percent = ask_float(
            "Partner share percentage (%): ",
            min_value=0,
            max_value=100
        )

        return mode, percent, None

    if mode == "custom_amount":
        amount_cents = ask_money(
            "Partner share per unit ($): ",
            min_cents=0
        )

        return mode, None, amount_cents

    return mode, None, None


def default_partner_share_percent():
    config = load_config()

    percent = config.get("default_partner_share_percent")

    if not isinstance(percent, (int, float)) or isinstance(percent, bool):
        raise ValueError(
            f"default_partner_share_percent in {CONFIG_FILE} "
            f"must be a number, found {percent!r}"
        )

    if not 0 <= percent <= 100:
        raise ValueError(
            f"default_partner_share_percent in {CONFIG_FILE} "
            f"must be between 0 and 100, found {percent}"
        )

    return percent


def partner_share_for(item):
    """The partner's cut for one unit of this item, in cents.

    This is the only place in PSells where a fraction of a cent can appear, so
    it is the only place that rounds. A percentage of a price does not have to
    land on a whole cent, and the result has to, because it is about to be
    frozen onto a sale and settled with a real person.

    The arithmetic goes through Decimal rather than float so that the rounding
    decision is made on an exact number. Rounding half away from zero rather
    than Python's half-to-even, because that is the convention people expect
    when money is being split.
    """
    mode = item["partner_share_mode"]

    if mode == "default":
        percent = default_partner_share_percent()

    elif mode == "custom_percent":
        percent = item["partner_share_percent"]

    elif mode == "custom_amount":
        return item["partner_share_amount_cents"]

    else:
        raise ValueError(f"Invalid partner share mode: {mode}")

    exact = Decimal(item["retail_price_cents"]) * Decimal(str(percent)) / 100

    return int(exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def dashboard_totals(connection):
    """The nine dashboard figures, computed by the database.

    Quantities are counts. Every money figure is in cents.

    COALESCE is not decoration. SUM over zero rows returns NULL rather than 0,
    so with an empty returns table the subtraction below would be done against
    None and raise.
    """
    def total(sql):
        return connection.execute(sql).fetchone()["total"]

    total_received = total(
        "SELECT COALESCE(SUM(quantity_received), 0) AS total FROM products"
    )
    total_sold = total(
        "SELECT COALESCE(SUM(quantity), 0) AS total FROM sales"
    )
    total_returned = total(
        "SELECT COALESCE(SUM(quantity), 0) AS total FROM returns"
    )
    total_revenue = total(
        "SELECT COALESCE(SUM(quantity * sale_price_cents), 0) AS total "
        "FROM sales"
    )
    total_partner_share = total(
        "SELECT COALESCE(SUM(quantity * partner_share_cents), 0) AS total "
        "FROM sales"
    )
    total_paid = total(
        "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM payments"
    )

    return {
        "total_received": total_received,
        "total_sold": total_sold,
        "total_available": total_received - total_sold - total_returned,
        "total_returned": total_returned,
        "total_revenue": total_revenue,
        "total_partner_share": total_partner_share,
        "total_profit": total_revenue - total_partner_share,
        "total_paid": total_paid,
        "balance_owing": total_partner_share - total_paid
    }


class SaleError(ValueError):
    """A sale that cannot be recorded, with a message safe to show a caller.

    Raised by create_sale rather than returned, so no caller can record a sale
    by ignoring a return value it forgot to check.
    """


class ProductNotFound(SaleError):
    """The product itself does not exist, rather than the sale being wrong.

    A separate type because the two are different problems with different
    answers: one means correct the id, the other means correct the sale. Callers
    that do not care can still catch SaleError and get both.
    """


def create_sale(connection, product_id, quantity, sale_price_cents, sale_date):
    """Record one sale and return the partner cut that was frozen onto it.

    This is the whole of recording a sale with none of the asking. record_sale
    is the same operation driven by a keyboard, and the API drives it from a
    request body; both end up here, so the rules below are enforced once and
    the partner cut is computed in one place.

    The checks repeat what the prompts already guarantee, which is deliberate.
    A caller that is not a prompt has guaranteed nothing.
    """
    product = connection.execute(
        "SELECT * FROM products_view WHERE id = %s",
        (product_id,)
    ).fetchone()

    if product is None:
        raise ProductNotFound(f"No product with id {product_id}.")

    available = product["quantity_available"]

    if available <= 0:
        raise SaleError(f"{product['name']} has no stock available to sell.")

    if quantity < 1:
        raise SaleError("Quantity must be at least 1.")

    if quantity > available:
        raise SaleError(
            f"Only {available} available, so {quantity} cannot be sold."
        )

    if sale_price_cents < 0:
        raise SaleError("Sale price cannot be negative.")

    # The schema refuses an impossible date too, but a constraint failure is
    # not a sentence anybody can act on, and the API would surface it as a
    # server error rather than as bad input.
    #
    # strptime reads 2026-9-3 as well as 2026-09-03. The date is written back
    # zero-padded, as ask_date does, so every caller hands the database the one
    # form, whatever the column would have accepted.
    try:
        sale_date = datetime.strptime(sale_date, "%Y-%m-%d").strftime(
            "%Y-%m-%d")
    except (ValueError, TypeError):
        raise SaleError(f"{sale_date!r} is not a date in YYYY-MM-DD form.")

    partner_cut = partner_share_for(product)

    # One insert. The product is not touched at all: units sold is derived from
    # this table, so there is no second value that could fall out of step.
    # The id is left out so the database's sequence assigns it.
    with connection.transaction():
        connection.execute(
            "INSERT INTO sales "
            "(date, item_id, quantity, sale_price_cents, partner_share_cents) "
            "VALUES (%s, %s, %s, %s, %s)",
            (sale_date, product_id, quantity, sale_price_cents, partner_cut)
        )

    return partner_cut



class ReturnError(ValueError):
    """A return that cannot be recorded, with a message safe to show a caller.

    Raised by create_return when the stock disagrees with a return that was
    otherwise well formed, as SaleError is by create_sale.
    """


def create_return(connection, product_id, quantity, return_date, notes):
    """Record units going back out of stock, and return the new return's id.

    The whole of recording a return with none of the asking. record_return is
    the same operation driven by a keyboard; the web form drives it from a
    request. The checks repeat what the prompts guarantee, for the reason
    create_sale gives: a caller that is not a prompt has guaranteed nothing.

    A return is its own row. The product is not touched: quantity_received
    means the units originally taken in, and units available is derived from
    received minus sold minus returned, so there is no second figure that could
    fall out of step. The date is written back zero-padded, as create_sale's is.

    Raises ProductNotFound for an id that does not exist, the same exception
    create_sale and update_product raise, and ReturnError for the rest.
    """
    product = connection.execute(
        "SELECT * FROM products_view WHERE id = %s",
        (product_id,)
    ).fetchone()

    if product is None:
        raise ProductNotFound(f"No product with id {product_id}.")

    available = product["quantity_available"]

    if available <= 0:
        raise ReturnError(
            f"{product['name']} has no stock available to return."
        )

    if not _is_whole_number(quantity) or quantity < 1:
        raise ReturnError("Quantity must be at least 1.")

    if quantity > available:
        raise ReturnError(
            f"Only {available} available, so {quantity} cannot be returned."
        )

    try:
        return_date = datetime.strptime(return_date, "%Y-%m-%d").strftime(
            "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ReturnError(f"{return_date!r} is not a date in YYYY-MM-DD form.")

    with connection.transaction():
        return connection.execute(
            "INSERT INTO returns (date, item_id, quantity, notes) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (return_date, product_id, quantity, (notes or "").strip())
        ).fetchone()["id"]

class PaymentError(ValueError):
    """A payment that cannot be recorded, with a message safe to show."""


def create_payment(connection, amount_cents, payment_date, notes):
    """Record one payment to the partner and return the new payment's id.

    The whole of recording a payment with none of the asking. record_payment is
    the same operation driven by a keyboard; the web form drives it from a
    request. A payment belongs to no product: it is money paid to the partner,
    and the balance owing is the partner share earned on sales minus every
    payment.

    A payment of zero is accepted. That is deliberate and was confirmed as
    wanted rather than tolerated; a test on the command line says so. A negative
    amount is refused. The date is written back zero-padded, as for a sale.
    """
    if not _is_whole_number(amount_cents) or amount_cents < 0:
        raise PaymentError("Amount cannot be negative.")

    try:
        payment_date = datetime.strptime(payment_date, "%Y-%m-%d").strftime(
            "%Y-%m-%d")
    except (ValueError, TypeError):
        raise PaymentError(
            f"{payment_date!r} is not a date in YYYY-MM-DD form."
        )

    with connection.transaction():
        return connection.execute(
            "INSERT INTO payments (date, amount_cents, notes) "
            "VALUES (%s, %s, %s) RETURNING id",
            (payment_date, amount_cents, (notes or "").strip())
        ).fetchone()["id"]

class DeleteRefused(ValueError):
    """A product that cannot be deleted, with the sentence saying why."""


def deletion_blocker(connection, product_id):
    """Why this product cannot be deleted, as a sentence, or None if it can.

    A product with sales or returns recorded against it keeps them: the foreign
    keys would refuse the delete anyway, but "FOREIGN KEY constraint failed" is
    not an answer to a person. Asked before offering to delete, so nobody is
    asked to confirm something that is then refused.
    """
    sale_count = connection.execute(
        "SELECT COUNT(*) AS n FROM sales WHERE item_id = %s",
        (product_id,)
    ).fetchone()["n"]

    return_count = connection.execute(
        "SELECT COUNT(*) AS n FROM returns WHERE item_id = %s",
        (product_id,)
    ).fetchone()["n"]

    blocking = []

    if sale_count:
        blocking.append(f"{sale_count} sale" + ("" if sale_count == 1 else "s"))

    if return_count:
        blocking.append(
            f"{return_count} return" + ("" if return_count == 1 else "s")
        )

    if not blocking:
        return None

    return f"This product has {' and '.join(blocking)} recorded against it."


def delete_product(connection, product_id):
    """Delete a product with no history, or raise saying why not.

    The whole of deleting with none of the asking. delete asks for a yes first;
    the web page's confirmation is its own page. The check is repeated here
    rather than trusted, and the database is the last word: if it still
    refuses, something points at the product that deletion_blocker does not
    know about, and the refusal is a sentence rather than a stack trace.

    Raises ProductNotFound for an id that does not exist, and DeleteRefused
    otherwise.
    """
    if connection.execute("SELECT 1 FROM products WHERE id = %s",
                          (product_id,)).fetchone() is None:
        raise ProductNotFound(f"No product with id {product_id}.")

    blocker = deletion_blocker(connection, product_id)

    if blocker is not None:
        raise DeleteRefused(blocker)

    # IntegrityError, the parent, not the particular refusal: PostgreSQL 18
    # reports ON DELETE RESTRICT as RestrictViolation where 16 reported
    # ForeignKeyViolation, and the sentence is the same whichever it was.
    try:
        with connection.transaction():
            connection.execute("DELETE FROM products WHERE id = %s",
                               (product_id,))
    except psycopg.errors.IntegrityError:
        raise DeleteRefused(
            "The database refused the deletion. Something still refers to "
            "this product, so nothing was removed."
        )

PARTNER_SHARE_MODES = ("default", "custom_percent", "custom_amount")


class ProductError(ValueError):
    """A product that cannot be stored, with every reason at once.

    problems maps a field name to a sentence safe to show a person. It holds
    every problem found, not just the first: the command line asks one question
    at a time and can stop at the first bad answer, but a form arrives whole,
    and making someone fix one field, resubmit and meet the next is a bad way to
    be told there were three.
    """

    def __init__(self, problems):
        self.problems = dict(problems)
        super().__init__(" ".join(self.problems.values()))


def _is_whole_number(value):
    # bool is a subclass of int, so True would otherwise pass as 1.
    return isinstance(value, int) and not isinstance(value, bool)


def product_problems(category, name, quantity_received, retail_discontinued,
                     retail_price_cents, listed_price_cents, condition,
                     partner_share_mode, partner_share_percent,
                     partner_share_amount_cents):
    """Every rule a new product must satisfy, as {field: sentence}.

    Empty when the product is acceptable. These are the rules add has always
    enforced through its prompts, and the ones the schema enforces again at the
    bottom, stated once here so that a caller with no prompts, a web form, is
    held to the same rules and told about them in sentences rather than by a
    constraint failure.

    A value of None means the caller could not read that field at all, and has
    already said so; it is skipped here rather than reported twice.
    """
    problems = {}

    for field, label, text in (("category", "Category", category),
                               ("name", "Name", name),
                               ("condition", "Condition", condition)):
        if text is not None and not str(text).strip():
            problems[field] = f"{label} cannot be blank."

    if quantity_received is not None and not (
            _is_whole_number(quantity_received) and quantity_received >= 1):
        problems["quantity_received"] = (
            "Quantity received must be a whole number, at least 1."
        )

    if retail_discontinued:
        # Zero is what discontinued means in the schema, not a price someone
        # typed, and the only mode that makes sense is a fixed amount: there is
        # no retail price left to take a percentage of.
        if retail_price_cents not in (None, 0):
            problems["retail_price"] = (
                "A product discontinued at retail has no retail price."
            )

        if partner_share_mode not in (None, "custom_amount"):
            problems["partner_share_mode"] = (
                "A product discontinued at retail takes a fixed partner "
                "amount per unit."
            )

    elif retail_price_cents is not None and not (
            _is_whole_number(retail_price_cents) and retail_price_cents >= 1):
        problems["retail_price"] = "Retail price must be at least $0.01."

    if listed_price_cents is not None and not (
            _is_whole_number(listed_price_cents) and listed_price_cents >= 0):
        problems["listed_price"] = "Listed price cannot be negative."

    if (partner_share_mode is not None
            and partner_share_mode not in PARTNER_SHARE_MODES):
        problems["partner_share_mode"] = (
            "Partner share mode must be default, custom_percent or "
            "custom_amount."
        )

    if partner_share_mode == "custom_percent":
        # A missing percentage is reported as required by create_product. The
        # range check also refuses nan and infinity, which float() accepts
        # from text: nan compares false with every number, so it is never
        # between 0 and 100, and infinity is never at most 100. Stored, nan
        # would become NULL and fail the schema's matrix constraint.
        if partner_share_percent is not None and not (
                isinstance(partner_share_percent, (int, float))
                and not isinstance(partner_share_percent, bool)
                and 0 <= partner_share_percent <= 100):
            problems["partner_share_percent"] = (
                "Partner share percentage must be a number from 0 to 100."
            )
    elif partner_share_percent is not None:
        problems["partner_share_percent"] = (
            "A partner share percentage belongs only to custom_percent."
        )

    if partner_share_mode == "custom_amount":
        # A missing amount is reported as required by create_product.
        if partner_share_amount_cents is not None and not (
                _is_whole_number(partner_share_amount_cents)
                and partner_share_amount_cents >= 0):
            problems["partner_share_amount"] = (
                "Partner share amount cannot be negative."
            )
    elif partner_share_amount_cents is not None:
        problems["partner_share_amount"] = (
            "A fixed partner amount belongs only to custom_amount."
        )

    return problems


def _every_product_problem(category, name, quantity_received,
                           retail_discontinued, retail_price_cents,
                           listed_price_cents, condition, partner_share_mode,
                           partner_share_percent, partner_share_amount_cents):
    """product_problems, plus a field that is None where one is needed.

    None means "could not be read", which only a caller parsing text can
    produce, and a product cannot be stored with a field missing.
    """
    problems = product_problems(
        category, name, quantity_received, retail_discontinued,
        retail_price_cents, listed_price_cents, condition,
        partner_share_mode, partner_share_percent, partner_share_amount_cents,
    )

    needed = [("category", category), ("name", name),
              ("quantity_received", quantity_received),
              ("retail_price", retail_price_cents),
              ("listed_price", listed_price_cents),
              ("condition", condition),
              ("partner_share_mode", partner_share_mode)]

    if partner_share_mode == "custom_percent":
        needed.append(("partner_share_percent", partner_share_percent))

    if partner_share_mode == "custom_amount":
        needed.append(("partner_share_amount", partner_share_amount_cents))

    for field, value in needed:
        if value is None:
            problems.setdefault(field, "This field is required.")

    return problems

def create_product(connection, category, name, quantity_received,
                   retail_discontinued, retail_price_cents, listed_price_cents,
                   condition, notes, partner_share_mode, partner_share_percent,
                   partner_share_amount_cents):
    """Store one new product and return the id the database gave it.

    The whole of adding a product with none of the asking. add is the same
    operation driven by a keyboard; the web form drives it from a request. Both
    end here, so the rules are checked once, by product_problems, and every
    problem is raised together in one ProductError.

    The checks repeat what add's prompts already guarantee, which is
    deliberate, as in create_sale: a caller that is not a prompt has guaranteed
    nothing. Text is stripped here too, so a caller that forgets cannot store
    leading or trailing spaces.
    """
    problems = _every_product_problem(
        category, name, quantity_received, retail_discontinued,
        retail_price_cents, listed_price_cents, condition,
        partner_share_mode, partner_share_percent, partner_share_amount_cents,
    )

    if problems:
        raise ProductError(problems)

    # The id is left out: the database's sequence assigns it, and refuses one
    # supplied here. A sequence never hands out the same id twice, so a deleted
    # product's id is never given to the next one.
    with connection.transaction():
        return connection.execute(
            "INSERT INTO products "
            "(category, name, quantity_received, retail_price_cents, "
            "listed_price_cents, retail_discontinued, partner_share_mode, "
            "partner_share_percent, partner_share_amount_cents, "
            "condition, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id",
            (category.strip(), name.strip(), quantity_received,
             retail_price_cents, listed_price_cents,
             1 if retail_discontinued else 0,
             partner_share_mode, partner_share_percent,
             partner_share_amount_cents, condition.strip(),
             (notes or "").strip())
        ).fetchone()["id"]


def _intake_floor_problem(connection, product_id, quantity_received):
    """The one rule an edit adds: received cannot fall below what has gone.

    Units sold and units returned have both left the original intake. Returns
    {} or {"quantity_received": sentence}. Raises ProductNotFound for an id that
    does not exist, which is checked first because nothing else about an edit
    means anything without the product.
    """
    product = connection.execute(
        "SELECT * FROM products_view WHERE id = %s",
        (product_id,)
    ).fetchone()

    if product is None:
        raise ProductNotFound(f"No product with id {product_id}.")

    gone = product["quantity_sold"] + product["quantity_returned"]

    if (_is_whole_number(quantity_received)
            and 1 <= quantity_received < gone):
        return {"quantity_received": (
            f"Quantity received cannot be less than {gone}, the units already "
            f"sold or returned."
        )}

    return {}

def update_product(connection, product_id, category, name, quantity_received,
                   retail_discontinued, retail_price_cents, listed_price_cents,
                   condition, notes, partner_share_mode, partner_share_percent,
                   partner_share_amount_cents):
    """Replace every field of one product with the values given.

    The whole of editing a product with none of the asking. edit is the same
    operation driven by a keyboard; the web edit form drives it from a request.
    Every value is given, not only the ones that changed: the command line's
    keep-current convention is how edit fills in the ones left alone, and a form
    arrives with every field anyway.

    The rules are create_product's, through the same _every_product_problem,
    plus one that only exists once a product has history: the units received
    cannot fall below the units already sold plus returned, which have both left
    the original intake. Every problem is raised at once in one ProductError.

    Sales are never touched. Each one froze its own partner cut when it
    happened, so changing a product's partner share here changes what later
    sales will take and nothing that has already been sold.

    Raises ProductNotFound for an id that does not exist, the same exception
    create_sale raises for one, because it is the same fact about the world.
    """
    problems = {
        **_intake_floor_problem(connection, product_id, quantity_received),
        **_every_product_problem(
            category, name, quantity_received, retail_discontinued,
            retail_price_cents, listed_price_cents, condition,
            partner_share_mode, partner_share_percent,
            partner_share_amount_cents,
        ),
    }

    if problems:
        raise ProductError(problems)

    with connection.transaction():
        connection.execute(
            "UPDATE products SET "
            "category = %s, name = %s, quantity_received = %s, "
            "retail_price_cents = %s, listed_price_cents = %s, "
            "retail_discontinued = %s, partner_share_mode = %s, "
            "partner_share_percent = %s, partner_share_amount_cents = %s, "
            "condition = %s, notes = %s "
            "WHERE id = %s",
            (category.strip(), name.strip(), quantity_received,
             retail_price_cents, listed_price_cents,
             1 if retail_discontinued else 0,
             partner_share_mode, partner_share_percent,
             partner_share_amount_cents, condition.strip(),
             (notes or "").strip(), product_id)
        )

# The fields a product form sends, by the names it sends them under. Every value
# arrives as text, and a field the person left empty arrives as "".
PRODUCT_FORM_FIELDS = (
    "category", "name", "quantity_received", "retail_discontinued",
    "retail_price", "listed_price", "condition", "notes",
    "partner_share_mode", "partner_share_percent", "partner_share_amount",
)

MONEY_TEXT_PROBLEM = "Please enter an amount in dollars, for example 12.50."


def read_product_text(fields):
    """Turn a product form's text into create_product's values.

    Returns (values, problems). A field that cannot be read becomes None in
    values, with a sentence in problems saying why; create_product then treats
    the None as required rather than reporting it twice.

    Money goes through parse_money, the only place text becomes cents. A field
    that does not apply to the choices made is ignored, as the command line
    never asks it: the retail price of a product discontinued at retail, which
    is zero by definition, and the percentage or amount of a mode that was not
    chosen.
    """
    text = {key: (fields.get(key) or "").strip() for key in PRODUCT_FORM_FIELDS}
    problems = {}

    def money(key):
        if not text[key]:
            problems[key] = "This field is required."
            return None

        try:
            return parse_money(text[key])
        except ValueError:
            problems[key] = MONEY_TEXT_PROBLEM
            return None

    quantity_received = None

    if not text["quantity_received"]:
        problems["quantity_received"] = "This field is required."
    else:
        try:
            quantity_received = int(text["quantity_received"])
        except ValueError:
            problems["quantity_received"] = (
                "Quantity received must be a whole number, at least 1."
            )

    # A ticked checkbox sends its value, "yes"; an unticked one sends nothing.
    if text["retail_discontinued"] not in ("", "yes"):
        problems["retail_discontinued"] = "Discontinued is either ticked or not."

    retail_discontinued = text["retail_discontinued"] == "yes"
    retail_price_cents = 0 if retail_discontinued else money("retail_price")

    mode = text["partner_share_mode"] or None
    percent = None
    amount_cents = None

    if mode == "custom_percent" and text["partner_share_percent"]:
        try:
            # nan and inf read as floats here and are refused by the range
            # check in product_problems.
            percent = float(text["partner_share_percent"])
        except ValueError:
            problems["partner_share_percent"] = (
                "Partner share percentage must be a number from 0 to 100."
            )

    if mode == "custom_amount" and text["partner_share_amount"]:
        amount_cents = money("partner_share_amount")

    values = {
        "category": text["category"],
        "name": text["name"],
        "quantity_received": quantity_received,
        "retail_discontinued": retail_discontinued,
        "retail_price_cents": retail_price_cents,
        "listed_price_cents": money("listed_price"),
        "condition": text["condition"],
        "notes": text["notes"],
        "partner_share_mode": mode,
        "partner_share_percent": percent,
        "partner_share_amount_cents": amount_cents,
    }

    return values, problems


def create_product_from_text(connection, fields):
    """Add a product from a form's text and return its new id.

    Every problem is reported at once: what could not be read, and every rule
    the readable fields break, in one ProductError. Nothing is stored unless
    there are none.
    """
    values, problems = read_product_text(fields)

    if problems:
        rule_values = {key: value for key, value in values.items()
                       if key != "notes"}
        raise ProductError({**_every_product_problem(**rule_values),
                            **problems})

    return create_product(connection, **values)


def product_form_text(product):
    """One stored product as the text an edit form starts from.

    The inverse of read_product_text: reading this text back gives the product's
    own values, so opening the edit form and saving it unchanged changes
    nothing. Money is written without the dollar sign, because that is what
    parse_money reads. A percentage is written with str(), which Python
    guarantees reads back as the identical float; a shortened form such as
    "33.3" for 33.333333 would quietly change it on the first save.
    """
    percent = product["partner_share_percent"]
    amount = product["partner_share_amount_cents"]
    discontinued = bool(product["retail_discontinued"])

    return {
        "category": product["category"],
        "name": product["name"],
        "quantity_received": str(product["quantity_received"]),
        "retail_discontinued": "yes" if discontinued else "",
        "retail_price": "" if discontinued else format_cents(
            product["retail_price_cents"], symbol=False),
        "listed_price": format_cents(product["listed_price_cents"],
                                     symbol=False),
        "condition": product["condition"],
        "notes": product["notes"],
        "partner_share_mode": product["partner_share_mode"],
        "partner_share_percent": "" if percent is None else str(percent),
        "partner_share_amount": "" if amount is None else format_cents(
            amount, symbol=False),
    }


def update_product_from_text(connection, product_id, fields):
    """Change a product from an edit form's text.

    As create_product_from_text, every problem at once: what could not be read,
    every rule the readable fields break, and the intake floor. Raises
    ProductNotFound for an id that does not exist.
    """
    values, problems = read_product_text(fields)

    if problems:
        rule_values = {key: value for key, value in values.items()
                       if key != "notes"}
        raise ProductError({
            **_intake_floor_problem(connection, product_id,
                                    values["quantity_received"]),
            **_every_product_problem(**rule_values),
            **problems,
        })

    update_product(connection, product_id, **values)


# The fields a sale form sends. As with a product form, every value is text.
SALE_FORM_FIELDS = ("quantity", "sale_price", "date")


class SaleInputError(SaleError):
    """A sale form whose text is wrong in itself, with a sentence per field.

    A SaleError, so a caller catching SaleError still catches it. Separate from
    the stock refusals create_sale raises, because the two have different
    answers: this one means correct what was typed, and a stock refusal means
    what was typed was fine and the stock disagrees with it.
    """

    def __init__(self, problems):
        self.problems = dict(problems)
        super().__init__(" ".join(self.problems.values()))


def _read_quantity_text(text, problems):
    """A quantity of whole units from a form, or None with a sentence added."""
    if not text:
        problems["quantity"] = "This field is required."
        return None

    try:
        quantity = int(text)
    except ValueError:
        quantity = None

    if quantity is None or quantity < 1:
        problems["quantity"] = "Quantity must be a whole number, at least 1."
        return None

    return quantity


def _read_date_text(text, problems):
    """A date from a form, read the way the command line's ask_date reads it.

    Blank means today. A date that parses is written back zero-padded, the only
    form the schema accepts. Otherwise None, with a sentence added.
    """
    if not text:
        return date.today().isoformat()

    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        problems["date"] = "Please enter a valid date in YYYY-MM-DD format."
        return None

def read_sale_text(fields):
    """Turn a sale form's text into create_sale's values.

    Returns (values, problems), as read_product_text does. The date is read the
    way the command line's ask_date reads it: blank means today, and a date
    that parses is written back in the zero-padded form the schema requires, so
    2026-9-3 is stored as 2026-09-03 rather than refused by a constraint.
    """
    text = {key: (fields.get(key) or "").strip() for key in SALE_FORM_FIELDS}
    problems = {}

    quantity = _read_quantity_text(text["quantity"], problems)

    sale_price_cents = None

    if not text["sale_price"]:
        problems["sale_price"] = "This field is required."
    else:
        try:
            sale_price_cents = parse_money(text["sale_price"])
        except ValueError:
            problems["sale_price"] = MONEY_TEXT_PROBLEM
        else:
            if sale_price_cents < 0:
                problems["sale_price"] = "Sale price cannot be negative."
                sale_price_cents = None

    sale_date = _read_date_text(text["date"], problems)

    values = {"quantity": quantity, "sale_price_cents": sale_price_cents,
              "sale_date": sale_date}

    return values, problems


def create_sale_from_text(connection, product_id, fields):
    """Record a sale from a form's text and return the partner cut frozen.

    Raises SaleInputError when the text is wrong in itself, and otherwise
    whatever create_sale raises: ProductNotFound, or SaleError when the stock
    disagrees with a sale that was well formed.
    """
    values, problems = read_sale_text(fields)

    if problems:
        raise SaleInputError(problems)

    return create_sale(connection, product_id, values["quantity"],
                       values["sale_price_cents"], values["sale_date"])


# The fields a return form sends.
RETURN_FORM_FIELDS = ("quantity", "date", "notes")


class ReturnInputError(ReturnError):
    """A return form whose text is wrong in itself, with a sentence per field.

    A ReturnError, as SaleInputError is a SaleError, and separate from the
    stock refusals for the same reason: correct what was typed, rather than the
    stock disagreeing with what was typed.
    """

    def __init__(self, problems):
        self.problems = dict(problems)
        super().__init__(" ".join(self.problems.values()))


def create_return_from_text(connection, product_id, fields):
    """Record a return from a form's text and return the new return's id.

    Quantity and date are read exactly as a sale form's are. Notes are free
    text and may be empty. Raises ReturnInputError when the text is wrong in
    itself, and otherwise whatever create_return raises.
    """
    text = {key: (fields.get(key) or "").strip() for key in RETURN_FORM_FIELDS}
    problems = {}

    quantity = _read_quantity_text(text["quantity"], problems)
    return_date = _read_date_text(text["date"], problems)

    if problems:
        raise ReturnInputError(problems)

    return create_return(connection, product_id, quantity, return_date,
                         text["notes"])


def all_payments(connection):
    """Every payment to the partner, oldest first."""
    return connection.execute(
        "SELECT * FROM payments ORDER BY id"
    ).fetchall()


# The fields a payment form sends.
PAYMENT_FORM_FIELDS = ("amount", "date", "notes")


class PaymentInputError(PaymentError):
    """A payment form whose text is wrong in itself, a sentence per field."""

    def __init__(self, problems):
        self.problems = dict(problems)
        super().__init__(" ".join(self.problems.values()))


def create_payment_from_text(connection, fields):
    """Record a payment from a form's text and return the new payment's id.

    The amount is read by parse_money and may be zero, as on the command line.
    The date is read as every form's date is. Raises PaymentInputError with a
    sentence per field when anything is wrong; a payment has no stock to
    disagree with, so there is no second kind of refusal.
    """
    text = {key: (fields.get(key) or "").strip() for key in PAYMENT_FORM_FIELDS}
    problems = {}

    amount_cents = None

    if not text["amount"]:
        problems["amount"] = "This field is required."
    else:
        try:
            amount_cents = parse_money(text["amount"])
        except ValueError:
            problems["amount"] = MONEY_TEXT_PROBLEM
        else:
            if amount_cents < 0:
                problems["amount"] = "Amount cannot be negative."

    payment_date = _read_date_text(text["date"], problems)

    if problems:
        raise PaymentInputError(problems)

    return create_payment(connection, amount_cents, payment_date,
                          text["notes"])

def view_dashboard(connection):
    totals = dashboard_totals(connection)

    print("Dashboard")
    print()
    print(f"Total received: {totals['total_received']}")
    print(f"Total sold: {totals['total_sold']}")
    print(f"Total available: {totals['total_available']}")
    print(f"Total returned: {totals['total_returned']}")
    print()
    print(f"Total revenue: {format_cents(totals['total_revenue'])}")
    print(f"Total profit: {format_cents(totals['total_profit'])}")
    print(
        f"Total partner share earned: "
        f"{format_cents(totals['total_partner_share'])}"
    )
    print(f"Total paid: {format_cents(totals['total_paid'])}")
    print(f"Balance owing: {format_cents(totals['balance_owing'])}")


def print_product(product):
    partner_cut = partner_share_for(product)

    print(f"ID: {product['id']}")
    print(f"Name: {product['name']}")
    print(f"Category: {product['category']}")
    print(f"Available: {product['quantity_available']}")
    print(f"Listed Price: {format_cents(product['listed_price_cents'])}")
    print(f"Partner Cut: {format_cents(partner_cut)}")
    print(f"Discontinued: {'Yes' if product['retail_discontinued'] else 'No'}")
    print(f"Condition: {product['condition']}")
    print()
def view_inventory(connection):
    products = all_products(connection)

    if not products:
        print("Inventory is empty.")
        return

    for product in products:
        print_product(product)


def find_items_by_name(inventory, name):
    matches = []

    for item in inventory:
        if name.lower() in item["name"].lower():
            matches.append(item)

    return matches


def find_items_by_name_or_category(inventory, term):
    """Products whose name or category contains the term, case-insensitively.

    Deliberately separate from find_items_by_name rather than replacing it.
    This one is for browsing, where a wide match is the point. Choosing a
    product to sell, edit or delete still matches on name only, because a wide
    match there would list an entire category before asking which one you meant,
    and then act on the answer.
    """
    matches = []

    for item in inventory:
        if (term.lower() in item["name"].lower()
                or term.lower() in item["category"].lower()):
            matches.append(item)

    return matches


def category_counts(connection):
    """Every category once, with how many products are in it, A to Z.

    Alphabetical rather than largest first, because this list exists to be
    scanned for a name you half remember.

    COLLATE "C" sorts by character code, as SQLite did: capitals before
    lowercase, the same on every server. PostgreSQL's default follows the
    server's locale, which can ignore case and punctuation and can differ
    between a laptop and CI. Decided at the move to PostgreSQL.
    """
    return connection.execute(
        "SELECT category, COUNT(*) AS products "
        "FROM products "
        "GROUP BY category "
        'ORDER BY category COLLATE "C"'
    ).fetchall()


def select_product(inventory, action_word):
    name = ask_text(
        f"Search for a product to {action_word}: "
    )

    matches = find_items_by_name(inventory, name)

    if not matches:
        print("No products found.")
        return None

    if len(matches) == 1:
        product = matches[0]

    else:
        print("Multiple products found:")

        for item in matches:
            print(
                f"ID: {item['id']} | "
                f"Name: {item['name']}"
            )

        valid_ids = [
            item["id"]
            for item in matches
        ]

        while True:
            product_id = ask_int(
                f"Enter the ID of the product to {action_word}: "
            )

            if product_id in valid_ids:
                break

            print(
                "Invalid ID. Please choose one of "
                "the IDs shown above."
            )

        product = next(
            item for item in inventory
            if item["id"] == product_id
        )

    return product
def list_categories(connection):
    rows = category_counts(connection)

    if not rows:
        print("Inventory is empty.")
        return

    width = max(len(row["category"]) for row in rows)

    print("Categories")
    print()

    for row in rows:
        print(f"{row['category']:<{width}}  {row['products']}")

    print()
    print(f"{len(rows)} categories, {sum(r['products'] for r in rows)} products")


def search(connection):
    products = all_products(connection)

    term = ask_text("Search by product name or category: ")
    matches = find_items_by_name_or_category(products, term)

    if not matches:
        print("No products found.")
        return

    for product in matches:
        print_product(product)


def add(connection):
    category = ask_text("Category: ")
    name = ask_text("Name: ")

    quantity_received = ask_int(
        "Quantity received: ",
        min_value=1
    )

    retail_discontinued = ask_choice(
        "Discontinued? (yes/no): ",
        ["yes", "no"]
    ) == "yes"

    if retail_discontinued:
        retail_price_cents = 0
    else:
        # At least one cent. Zero is reserved for products discontinued at
        # retail, and the database enforces that, so a zero entered here would
        # be refused on insert rather than stored.
        retail_price_cents = ask_money(
            "Retail price: ",
            min_cents=1
        )

    listed_price_cents = ask_money(
        "Listed price: ",
        min_cents=0
    )

    condition = ask_text("Condition: ")
    notes = ask_optional_text("Notes: ")

    mode, percent, amount_cents = ask_partner_share(retail_discontinued)

    create_product(
        connection, category, name, quantity_received, retail_discontinued,
        retail_price_cents, listed_price_cents, condition, notes,
        mode, percent, amount_cents,
    )

    print("Product added successfully.")


def edit(connection):
    products = all_products(connection)

    if not products:
        print("Inventory is empty.")
        return

    product = select_product(products, "edit")

    if product is None:
        return

    print("Product selected:")
    print_product(product)

    category = ask_edit_text("Category", product["category"])
    name = ask_edit_text("Name", product["name"])

    # Units already sold plus units already returned have both left the original
    # intake, so the intake cannot be corrected to less than their sum.
    gone = product["quantity_sold"] + product["quantity_returned"]

    quantity_received = ask_edit_number(
        "Quantity received",
        product["quantity_received"],
        int,
        min_value=max(1, gone)
    )

    was_discontinued = bool(product["retail_discontinued"])

    retail_discontinued = ask_edit_choice(
        "Discontinued? (yes/no)",
        "yes" if was_discontinued else "no",
        ["yes", "no"]
    ) == "yes"

    if retail_discontinued:
        retail_price_cents = 0

    elif was_discontinued:
        # Coming back to retail, so there is no previous price to offer as a
        # default. Zero is not allowed, since zero means discontinued.
        retail_price_cents = ask_money(
            "Retail price: ",
            min_cents=1
        )

    else:
        retail_price_cents = ask_edit_money(
            "Retail price",
            product["retail_price_cents"],
            min_cents=1
        )

    listed_price_cents = ask_edit_money(
        "Listed price",
        product["listed_price_cents"],
        min_cents=0
    )

    condition = ask_edit_text("Condition", product["condition"])
    notes = ask_edit_text("Notes", product["notes"])

    # Partner share. Keep whatever the product already has unless something
    # forces a change or the user asks for one.
    mode = product["partner_share_mode"]
    percent = product["partner_share_percent"]
    amount_cents = product["partner_share_amount_cents"]

    if retail_discontinued and not was_discontinued:
        # Newly discontinued at retail. A percentage of a price that no longer
        # exists is meaningless, so the fixed amount is forced rather than
        # offered. A product already on a fixed amount keeps it.
        if mode != "custom_amount":
            mode, percent, amount_cents = ask_partner_share(True)

    else:
        if not retail_discontinued and not was_discontinued:
            print(f"Current partner-share mode: {mode}")

            if mode == "custom_percent":
                print(f"Current partner-share percentage: {percent}")
            elif mode == "custom_amount":
                print(
                    f"Current partner-share amount: "
                    f"{format_cents(amount_cents)}"
                )

        change = ask_choice(
            "Change partner share? (yes/no): ",
            ["yes", "no"]
        )

        if change == "yes":
            mode, percent, amount_cents = ask_partner_share(retail_discontinued)

    update_product(
        connection, product["id"], category, name, quantity_received,
        retail_discontinued, retail_price_cents, listed_price_cents,
        condition, notes, mode, percent, amount_cents,
    )

    print("Product updated successfully.")


def delete(connection):
    products = all_products(connection)

    if not products:
        print("Inventory is empty.")
        return

    product = select_product(products, "delete")

    if product is None:
        return

    print("Product selected:")
    print_product(product)

    # Ask what is pointing at this product before offering to delete it, so
    # nobody is asked to confirm something that is then refused.
    blocker = deletion_blocker(connection, product["id"])

    if blocker is not None:
        print(blocker)
        print("Deleting it would lose that history, so it is refused.")
        print("If you no longer stock it, leaving it in place costs nothing.")
        return

    confirmation = ask_choice(
        "Delete this product? (yes/no): ",
        ["yes", "no"]
    )

    if confirmation == "no":
        print("Cancelled.")
        return

    try:
        delete_product(connection, product["id"])
    except DeleteRefused:
        # The check above should have caught this. If it did not, something
        # points at this product that the check does not know about, and a
        # sentence beats a stack trace.
        print("The database refused the deletion. Something still refers to")
        print("this product, so nothing was removed.")
        return

    print("Product deleted.")


def record_sale(connection):
    products = all_products(connection)

    if not products:
        print("Inventory is empty.")
        return

    product = select_product(products, "sell")

    if product is None:
        return

    available = product["quantity_available"]

    if available <= 0:
        print("No stock available to sell.")
        return

    quantity = ask_int(
        "Quantity sold: ",
        min_value=1,
        max_value=available
    )

    sale_price_cents = ask_money(
        "Sale price per unit ($): ",
        min_cents=0
    )

    sale_date = ask_date("Date")

    partner_cut = partner_share_for(product)

    print()
    print("Sale information:")
    print(f"Product: {product['name']}")
    print(f"Quantity sold: {quantity}")
    print(f"Sale price per unit: {format_cents(sale_price_cents)}")
    print(f"Date: {sale_date}")
    print(f"Partner cut per unit: {format_cents(partner_cut)}")

    # The prompts above collected the answers. Recording the sale is create_sale,
    # which the API calls with the same arguments from a request body. The
    # partner cut is computed there as well as above, deliberately: the figure
    # printed in the summary is worked out from the same product row by the same
    # function, and leaving that line where it is keeps this output in the order
    # it has always been in.
    create_sale(
        connection,
        product["id"],
        quantity,
        sale_price_cents,
        sale_date
    )

    print("Sale recorded.")


def record_return(connection):
    products = all_products(connection)

    if not products:
        print("Inventory is empty.")
        return

    product = select_product(products, "return")

    if product is None:
        return

    available = product["quantity_available"]

    if available <= 0:
        print("No stock available to return.")
        return

    quantity = ask_int(
        "Quantity returned: ",
        min_value=1,
        max_value=available
    )

    return_date = ask_date("Date")
    notes = ask_optional_text("Notes: ")

    # The intake quantity is no longer reduced. It means units originally
    # received, and this return is recorded as its own fact, by create_return.
    create_return(connection, product["id"], quantity, return_date, notes)

    print("Return recorded.")


def record_payment(connection):
    payment_date = ask_date("Date")

    amount_cents = ask_money(
        "Amount ($): ",
        min_cents=0
    )

    notes = ask_optional_text("Notes: ")

    create_payment(connection, amount_cents, payment_date, notes)

    print("Payment recorded.")


def main():
    try:
        default_partner_share_percent()
    except (FileNotFoundError, ValueError) as error:
        print(f"Configuration error: {error}")
        sys.exit(1)

    try:
        connection = connect()
    except DatabaseUnavailable as error:
        print(f"Database error: {error}")
        sys.exit(1)

    while True:
        choice = input(
            "Choose an option!\n"
            "0: Quit\n"
            "1: View Dashboard\n"
            "2: View Inventory\n"
            "3: List Categories\n"
            "4: Search\n"
            "5: Add\n"
            "6: Edit\n"
            "7: Delete\n"
            "8: Record Sale\n"
            "9: Record Return\n"
            "10: Record Payment\n"
        )

        if choice == "0":
            break

        elif choice == "1":
            view_dashboard(connection)

        elif choice == "2":
            view_inventory(connection)

        elif choice == "3":
            list_categories(connection)

        elif choice == "4":
            search(connection)

        elif choice == "5":
            add(connection)

        elif choice == "6":
            edit(connection)

        elif choice == "7":
            delete(connection)

        elif choice == "8":
            record_sale(connection)

        elif choice == "9":
            record_return(connection)

        elif choice == "10":
            record_payment(connection)

        else:
            print("Invalid input try again!\n")

    connection.close()


if __name__ == "__main__":
    main()