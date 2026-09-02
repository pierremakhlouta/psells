import os
import json
from datetime import date, datetime


INVENTORY_FILE = "data/inventory.json"
SALES_FILE = "data/sales.json"
RETURNS_FILE = "data/returns.json"
PAYMENTS_FILE = "data/payments.json"
CONFIG_FILE = "data/config.json"


def load_data(filepath):
    if not os.path.exists(filepath):
        return []

    with open(filepath) as f:
        return json.load(f)


def save_data(data, filepath):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def next_id(records):
    if not records:
        return 1

    return max(record["id"] for record in records) + 1


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
    mode = item["partner_share_mode"]
    retail_price = item["retail_price"]

    if mode == "default":
        return (default_partner_share_percent() / 100) * retail_price

    elif mode == "custom_percent":
        return (item["partner_share_value"] / 100) * retail_price

    elif mode == "custom_amount":
        return item["partner_share_value"]

    else:
        raise ValueError(f"Invalid partner share mode: {mode}")
def view_dashboard():
    inventory = load_data(INVENTORY_FILE)
    sales = load_data(SALES_FILE)
    returns = load_data(RETURNS_FILE)
    payments = load_data(PAYMENTS_FILE)

    total_received = sum(
        product["quantity_received"]
        for product in inventory
    )

    total_sold = sum(
        product["quantity_sold"]
        for product in inventory
    )

    total_available = total_received - total_sold

    total_returned = sum(
        item["quantity"]
        for item in returns
    )

    total_revenue = sum(
        sale["quantity"] * sale["sale_price"]
        for sale in sales
    )

    total_partner_share = sum(
        sale["quantity"] * sale["partner_share"]
        for sale in sales
    )

    total_profit = total_revenue - total_partner_share

    total_paid = sum(
        payment["amount"]
        for payment in payments
    )

    balance_owing = total_partner_share - total_paid

    print("Dashboard")
    print()
    print(f"Total received: {total_received}")
    print(f"Total sold: {total_sold}")
    print(f"Total available: {total_available}")
    print(f"Total returned: {total_returned}")
    print()
    print(f"Total revenue: ${total_revenue:.2f}")
    print(f"Total profit: ${total_profit:.2f}")
    print(f"Total partner share earned: ${total_partner_share:.2f}")
    print(f"Total paid: ${total_paid:.2f}")
    print(f"Balance owing: ${balance_owing:.2f}")


def print_product(product):
    available = (
        product["quantity_received"]
        - product["quantity_sold"]
    )

    partner_cut = partner_share_for(product)

    print(f"ID: {product['id']}")
    print(f"Name: {product['name']}")
    print(f"Category: {product['category']}")
    print(f"Available: {available}")
    print(f"Listed Price: ${product['listed_price']:.2f}")
    print(f"Partner Cut: ${partner_cut:.2f}")
    print(f"Discontinued: {'Yes' if product.get('discontinued', False) else 'No'}")
    print(f"Condition: {product['condition']}")
    print()
def view_inventory():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    for product in inventory:
        print_product(product)


def find_items_by_name(inventory, name):
    matches = []

    for item in inventory:
        if name.lower() in item["name"].lower():
            matches.append(item)

    return matches


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
def search():
    inventory = load_data(INVENTORY_FILE)

    name = ask_text("Search for a product: ")
    matches = find_items_by_name(inventory, name)

    if not matches:
        print("No products found.")
        return

    for product in matches:
        print_product(product)


def add():
    category = ask_text("Category: ")
    name = ask_text("Name: ")

    quantity_received = ask_int(
        "Quantity received: ",
        min_value=1
    )

    discontinued = ask_choice(
        "Discontinued? (yes/no): ",
        ["yes", "no"]
    ) == "yes"

    if discontinued:
        retail_price = 0.0
    else:
        retail_price = ask_float(
            "Retail price: ",
            min_value=0
        )

    listed_price = ask_float(
        "Listed price: ",
        min_value=0
    )

    condition = ask_text("Condition: ")
    notes = ask_optional_text("Notes: ")

    if discontinued:
        partner_share_mode = "custom_amount"
        partner_share_value = ask_float(
            "Partner share per unit ($): ",
            min_value=0
        )
    else:
        partner_share_mode = ask_choice(
            "Partner-share mode "
            "(default/custom_percent/custom_amount): ",
            ["default", "custom_percent", "custom_amount"]
        )

        partner_share_value = None

        if partner_share_mode == "custom_percent":
            partner_share_value = ask_float(
                "Partner share percentage (%): ",
                min_value=0,
                max_value=100
            )

        elif partner_share_mode == "custom_amount":
            partner_share_value = ask_float(
                "Partner share per unit ($): ",
                min_value=0
            )

    inventory = load_data(INVENTORY_FILE)
    product_id = next_id(inventory)

    product = {
        "id": product_id,
        "category": category,
        "name": name,
        "quantity_received": quantity_received,
        "retail_price": retail_price,
        "listed_price": listed_price,
        "condition": condition,
        "notes": notes,
        "quantity_sold": 0,
        "discontinued": discontinued,
        "partner_share_mode": partner_share_mode
    }

    if partner_share_value is not None:
        product["partner_share_value"] = partner_share_value

    inventory.append(product)

    save_data(inventory, INVENTORY_FILE)

    print("Product added successfully.")


def edit():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    product = select_product(inventory, "edit")

    if product is None:
        return

    print("Product selected:")
    print_product(product)

    product["category"] = ask_edit_text(
        "Category",
        product["category"]
    )

    product["name"] = ask_edit_text(
        "Name",
        product["name"]
    )

    product["quantity_received"] = ask_edit_number(
        "Quantity received",
        product["quantity_received"],
        int,
        min_value=max(1, product["quantity_sold"])
    )

    was_discontinued = product.get("discontinued", False)

    current_discontinued = "yes" if was_discontinued else "no"

    discontinued_choice = ask_edit_choice(
        "Discontinued? (yes/no)",
        current_discontinued,
        ["yes", "no"]
    )

    discontinued = discontinued_choice == "yes"

    if discontinued:
        product["retail_price"] = 0.0
    else:
        if was_discontinued:
            product["retail_price"] = ask_float(
                "Retail price: ",
                min_value=0
            )
        else:
            product["retail_price"] = ask_edit_number(
                "Retail price",
                product["retail_price"],
                float,
                min_value=0
            )

    product["listed_price"] = ask_edit_number(
        "Listed price",
        product["listed_price"],
        float,
        min_value=0
    )

    product["condition"] = ask_edit_text(
        "Condition",
        product["condition"]
    )

    product["notes"] = ask_edit_text(
        "Notes",
        product["notes"]
    )

    if not was_discontinued and discontinued:
        if product["partner_share_mode"] != "custom_amount":
            partner_share_value = ask_float(
                "Partner share per unit ($): ",
                min_value=0
            )

            product["partner_share_mode"] = "custom_amount"
            product["partner_share_value"] = partner_share_value

    elif was_discontinued and not discontinued:
        change_partner_share = ask_choice(
            "Change partner share? (yes/no): ",
            ["yes", "no"]
        )

        if change_partner_share == "yes":
            partner_share_mode = ask_choice(
                "Partner-share mode "
                "(default/custom_percent/custom_amount): ",
                ["default", "custom_percent", "custom_amount"]
            )

            if partner_share_mode == "default":
                product["partner_share_mode"] = "default"
                product.pop("partner_share_value", None)

            elif partner_share_mode == "custom_percent":
                partner_share_value = ask_float(
                    "Partner share percentage (%): ",
                    min_value=0,
                    max_value=100
                )

                product["partner_share_mode"] = "custom_percent"
                product["partner_share_value"] = partner_share_value

            else:
                partner_share_value = ask_float(
                    "Partner share per unit ($): ",
                    min_value=0
                )

                product["partner_share_mode"] = "custom_amount"
                product["partner_share_value"] = partner_share_value

    elif discontinued:
        change_partner_share = ask_choice(
            "Change partner share? (yes/no): ",
            ["yes", "no"]
        )

        if change_partner_share == "yes":
            partner_share_value = ask_float(
                "Partner share per unit ($): ",
                min_value=0
            )

            product["partner_share_mode"] = "custom_amount"
            product["partner_share_value"] = partner_share_value

    else:
        print(
            f"Current partner-share mode: "
            f"{product['partner_share_mode']}"
        )

        if product["partner_share_mode"] != "default":
            print(
                f"Current partner-share value: "
                f"{product['partner_share_value']}"
            )

        change_partner_share = ask_choice(
            "Change partner share? (yes/no): ",
            ["yes", "no"]
        )

        if change_partner_share == "yes":
            partner_share_mode = ask_choice(
                "Partner-share mode "
                "(default/custom_percent/custom_amount): ",
                ["default", "custom_percent", "custom_amount"]
            )

            if partner_share_mode == "default":
                product["partner_share_mode"] = "default"
                product.pop("partner_share_value", None)

            elif partner_share_mode == "custom_percent":
                partner_share_value = ask_float(
                    "Partner share percentage (%): ",
                    min_value=0,
                    max_value=100
                )

                product["partner_share_mode"] = "custom_percent"
                product["partner_share_value"] = partner_share_value

            else:
                partner_share_value = ask_float(
                    "Partner share per unit ($): ",
                    min_value=0
                )

                product["partner_share_mode"] = "custom_amount"
                product["partner_share_value"] = partner_share_value

    product["discontinued"] = discontinued

    save_data(inventory, INVENTORY_FILE)

    print("Product updated successfully.")
def delete():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    product = select_product(inventory, "delete")

    if product is None:
        return

    print("Product selected:")
    print_product(product)

    confirmation = ask_choice(
        "Delete this product? (yes/no): ",
        ["yes", "no"]
    )

    if confirmation == "no":
        print("Cancelled.")
        return

    inventory = [
        item for item in inventory
        if item["id"] != product["id"]
    ]

    save_data(inventory, INVENTORY_FILE)

    print("Product deleted.")


def record_sale():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    product = select_product(inventory, "sell")

    if product is None:
        return

    available = (
        product["quantity_received"]
        - product["quantity_sold"]
    )

    if available <= 0:
        print("No stock available to sell.")
        return

    quantity = ask_int(
        "Quantity sold: ",
        min_value=1,
        max_value=available
    )

    sale_price = ask_float(
        "Sale price per unit ($): ",
        min_value=0
    )

    sale_date = ask_date("Date")

    partner_cut = partner_share_for(product)

    print()
    print("Sale information:")
    print(f"Product: {product['name']}")
    print(f"Quantity sold: {quantity}")
    print(f"Sale price per unit: ${sale_price:.2f}")
    print(f"Date: {sale_date}")
    print(f"Partner cut per unit: ${partner_cut:.2f}")

    product["quantity_sold"] += quantity

    save_data(inventory, INVENTORY_FILE)

    sales = load_data(SALES_FILE)

    sale = {
        "id": next_id(sales),
        "date": sale_date,
        "item_id": product["id"],
        "quantity": quantity,
        "sale_price": sale_price,
        "partner_share": partner_cut
    }

    sales.append(sale)

    save_data(sales, SALES_FILE)

    print("Sale recorded.")
def record_return():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    product = select_product(inventory, "return")

    if product is None:
        return

    available = (
        product["quantity_received"]
        - product["quantity_sold"]
    )

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

    product["quantity_received"] -= quantity

    save_data(inventory, INVENTORY_FILE)

    returns = load_data(RETURNS_FILE)

    return_record = {
        "id": next_id(returns),
        "date": return_date,
        "item_id": product["id"],
        "quantity": quantity,
        "notes": notes
    }

    returns.append(return_record)

    save_data(returns, RETURNS_FILE)

    print("Return recorded.")


def record_payment():
    payments = load_data(PAYMENTS_FILE)

    payment_date = ask_date("Date")

    amount = ask_float(
        "Amount ($): ",
        min_value=0
    )

    notes = ask_optional_text("Notes: ")

    payment = {
        "id": next_id(payments),
        "date": payment_date,
        "amount": amount,
        "notes": notes
    }

    payments.append(payment)

    save_data(payments, PAYMENTS_FILE)

    print("Payment recorded.")


while True:
    choice = input(
        "Choose an option!\n"
        "0: Quit\n"
        "1: View Dashboard\n"
        "2: View Inventory\n"
        "3: Search\n"
        "4: Add\n"
        "5: Edit\n"
        "6: Delete\n"
        "7: Record Sale\n"
        "8: Record Return\n"
        "9: Record Payment\n"
    )

    if choice == "0":
        break

    elif choice == "1":
        view_dashboard()

    elif choice == "2":
        view_inventory()

    elif choice == "3":
        search()

    elif choice == "4":
        add()

    elif choice == "5":
        edit()

    elif choice == "6":
        delete()

    elif choice == "7":
        record_sale()

    elif choice == "8":
        record_return()

    elif choice == "9":
        record_payment()

    else:
        print("Invalid input try again!\n")
