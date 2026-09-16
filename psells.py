import os
import json
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CONFIG_FILE = "data/config.json"
DB_FILE = "data/psells.db"


def connect():
    """Open the database and hand back a connection that is ready to use.

    Both settings below are per connection, not per database, so every
    connection the application opens has to apply them again.

    PRAGMA foreign_keys goes first, before anything can open a transaction,
    because SQLite ignores the pragma inside one and reports no error. Without
    it the foreign keys in the schema enforce nothing.

    row_factory makes a row readable by column name, so product["name"] keeps
    working. Without it a row is a plain tuple and the same code would have to
    say product[2].
    """
    connection = sqlite3.connect(DB_FILE)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row

    return connection


def all_products(connection):
    """Every product, with its derived quantities, in id order.

    Always read through products_view rather than the products table, because
    quantity_sold, quantity_returned and quantity_available only exist there.

    ORDER BY is not decoration. Without it SQLite makes no promise about the
    order rows come back in. It happens to match id order today, which is
    exactly the kind of accident that changes silently later.
    """
    return connection.execute(
        "SELECT * FROM products_view ORDER BY id"
    ).fetchall()


def format_cents(cents):
    """Format a whole number of cents as dollars, for display only.

    Deliberately integer arithmetic. Dividing by 100 would turn money back into
    a float at the last moment, which is the one thing the storage decision was
    meant to stop. Handles a negative figure, which balance owing can be.
    """
    sign = "-" if cents < 0 else ""
    cents = abs(cents)

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
            print(f"Value must be at least ${format_cents(min_cents)}.")
            continue

        if max_cents is not None and cents > max_cents:
            print(f"Value must be at most ${format_cents(max_cents)}.")
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
            print(f"Value must be at least ${format_cents(min_cents)}.")
            continue

        if max_cents is not None and cents > max_cents:
            print(f"Value must be at most ${format_cents(max_cents)}.")
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
        return connection.execute(sql).fetchone()[0]

    total_received = total(
        "SELECT COALESCE(SUM(quantity_received), 0) FROM products"
    )
    total_sold = total(
        "SELECT COALESCE(SUM(quantity), 0) FROM sales"
    )
    total_returned = total(
        "SELECT COALESCE(SUM(quantity), 0) FROM returns"
    )
    total_revenue = total(
        "SELECT COALESCE(SUM(quantity * sale_price_cents), 0) FROM sales"
    )
    total_partner_share = total(
        "SELECT COALESCE(SUM(quantity * partner_share_cents), 0) FROM sales"
    )
    total_paid = total(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM payments"
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


def view_dashboard(connection):
    totals = dashboard_totals(connection)

    print("Dashboard")
    print()
    print(f"Total received: {totals['total_received']}")
    print(f"Total sold: {totals['total_sold']}")
    print(f"Total available: {totals['total_available']}")
    print(f"Total returned: {totals['total_returned']}")
    print()
    print(f"Total revenue: ${format_cents(totals['total_revenue'])}")
    print(f"Total profit: ${format_cents(totals['total_profit'])}")
    print(
        f"Total partner share earned: "
        f"${format_cents(totals['total_partner_share'])}"
    )
    print(f"Total paid: ${format_cents(totals['total_paid'])}")
    print(f"Balance owing: ${format_cents(totals['balance_owing'])}")


def print_product(product):
    partner_cut = partner_share_for(product)

    print(f"ID: {product['id']}")
    print(f"Name: {product['name']}")
    print(f"Category: {product['category']}")
    print(f"Available: {product['quantity_available']}")
    print(f"Listed Price: ${format_cents(product['listed_price_cents'])}")
    print(f"Partner Cut: ${format_cents(partner_cut)}")
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
    """
    return connection.execute(
        "SELECT category, COUNT(*) AS products "
        "FROM products "
        "GROUP BY category "
        "ORDER BY category"
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

    # The id is left out so SQLite assigns it, the same way it did during the
    # migration.
    with connection:
        connection.execute(
            "INSERT INTO products "
            "(category, name, quantity_received, retail_price_cents, "
            "listed_price_cents, retail_discontinued, partner_share_mode, "
            "partner_share_percent, partner_share_amount_cents, "
            "condition, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (category, name, quantity_received, retail_price_cents,
             listed_price_cents, 1 if retail_discontinued else 0,
             mode, percent, amount_cents, condition, notes)
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
                    f"${format_cents(amount_cents)}"
                )

        change = ask_choice(
            "Change partner share? (yes/no): ",
            ["yes", "no"]
        )

        if change == "yes":
            mode, percent, amount_cents = ask_partner_share(retail_discontinued)

    with connection:
        connection.execute(
            "UPDATE products SET "
            "category = ?, name = ?, quantity_received = ?, "
            "retail_price_cents = ?, listed_price_cents = ?, "
            "retail_discontinued = ?, partner_share_mode = ?, "
            "partner_share_percent = ?, partner_share_amount_cents = ?, "
            "condition = ?, notes = ? "
            "WHERE id = ?",
            (category, name, quantity_received, retail_price_cents,
             listed_price_cents, 1 if retail_discontinued else 0,
             mode, percent, amount_cents, condition, notes,
             product["id"])
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

    # Ask what is pointing at this product before offering to delete it. The
    # foreign keys would refuse it anyway, but "FOREIGN KEY constraint failed"
    # is not an answer to a person standing at a menu.
    sale_count = connection.execute(
        "SELECT COUNT(*) FROM sales WHERE item_id = ?",
        (product["id"],)
    ).fetchone()[0]

    return_count = connection.execute(
        "SELECT COUNT(*) FROM returns WHERE item_id = ?",
        (product["id"],)
    ).fetchone()[0]

    blocking = []

    if sale_count:
        blocking.append(f"{sale_count} sale" + ("" if sale_count == 1 else "s"))

    if return_count:
        blocking.append(
            f"{return_count} return" + ("" if return_count == 1 else "s")
        )

    if blocking:
        print(f"This product has {' and '.join(blocking)} recorded against it.")
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
        with connection:
            connection.execute(
                "DELETE FROM products WHERE id = ?",
                (product["id"],)
            )
    except sqlite3.IntegrityError:
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
    print(f"Sale price per unit: ${format_cents(sale_price_cents)}")
    print(f"Date: {sale_date}")
    print(f"Partner cut per unit: ${format_cents(partner_cut)}")

    # One insert. The product is not touched at all: units sold is derived from
    # this table now, so there is no second value that could fall out of step.
    # The id is left out so SQLite assigns it.
    with connection:
        connection.execute(
            "INSERT INTO sales "
            "(date, item_id, quantity, sale_price_cents, partner_share_cents) "
            "VALUES (?, ?, ?, ?, ?)",
            (sale_date, product["id"], quantity, sale_price_cents, partner_cut)
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
    # received, and this return is recorded as its own fact.
    with connection:
        connection.execute(
            "INSERT INTO returns (date, item_id, quantity, notes) "
            "VALUES (?, ?, ?, ?)",
            (return_date, product["id"], quantity, notes)
        )

    print("Return recorded.")


def record_payment(connection):
    payment_date = ask_date("Date")

    amount_cents = ask_money(
        "Amount ($): ",
        min_cents=0
    )

    notes = ask_optional_text("Notes: ")

    with connection:
        connection.execute(
            "INSERT INTO payments (date, amount_cents, notes) "
            "VALUES (?, ?, ?)",
            (payment_date, amount_cents, notes)
        )

    print("Payment recorded.")


def main():
    try:
        default_partner_share_percent()
    except (FileNotFoundError, ValueError) as error:
        print(f"Configuration error: {error}")
        sys.exit(1)

    if not os.path.exists(DB_FILE):
        print(
            f"Database error: {DB_FILE} not found. "
            f"Run migrate_to_sqlite.py first."
        )
        sys.exit(1)

    connection = connect()

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