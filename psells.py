import os
import json


INVENTORY_FILE = "data/inventory.json"
SALES_FILE = "data/sales.json"
RETURNS_FILE = "data/returns.json"
PAYMENTS_FILE = "data/payments.json"


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


def partner_share_for(item):
    mode = item["partner_share_mode"]
    retail_price = item["retail_price"]

    if mode == "default":
        return 0.35 * retail_price

    elif mode == "custom_percent":
        return (item["partner_share_value"] / 100) * retail_price

    elif mode == "custom_amount":
        return item["partner_share_value"]

    else:
        raise ValueError(f"Invalid partner share mode: {mode}")


def view_dashboard():
    pass


def print_product(product):
    available = product["quantity_received"] - product["quantity_sold"]
    partner_cut = partner_share_for(product)

    print(f"ID: {product['id']}")
    print(f"Name: {product['name']}")
    print(f"Category: {product['category']}")
    print(f"Available: {available}")
    print(f"Listed Price: ${product['listed_price']:.2f}")
    print(f"Partner Cut: ${partner_cut:.2f}")
    print(f"Condition: {product['condition']}")
    print()


def view_inventory():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    for product in inventory:
        print_product(product)


def find_items_by_name(name):
    inventory = load_data(INVENTORY_FILE)
    matches = []

    for item in inventory:
        if name.lower() in item["name"].lower():
            matches.append(item)

    return matches


def search():
    name = ask_text("Search for a product: ")
    matches = find_items_by_name(name)

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

    partner_share_mode = ask_choice(
        "Partner-share mode (default/custom_percent/custom_amount): ",
        ["default", "custom_percent", "custom_amount"]
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
        "partner_share_mode": partner_share_mode
    }

    if partner_share_mode == "custom_percent":
        partner_share_value = ask_float(
            "Partner share percentage (%): ",
            min_value=0,
            max_value=100
        )

        product["partner_share_value"] = partner_share_value

    elif partner_share_mode == "custom_amount":
        partner_share_value = ask_float(
            "Partner share per unit ($): ",
            min_value=0
        )

        product["partner_share_value"] = partner_share_value

    inventory.append(product)

    save_data(inventory, INVENTORY_FILE)

    print("Product added successfully.")


def edit():
    inventory = load_data(INVENTORY_FILE)

    if not inventory:
        print("Inventory is empty.")
        return

    name = ask_text("Search for a product to edit: ")

    matches = []

    for item in inventory:
        if name.lower() in item["name"].lower():
            matches.append(item)

    if not matches:
        print("No products found.")
        return

    if len(matches) > 1:
        print("Multiple products found:")

        for item in matches:
            print(f"ID: {item['id']} | Name: {item['name']}")

        valid_ids = [item["id"] for item in matches]

        while True:
            selected_id = ask_int(
                "Enter the ID of the product to edit: "
            )

            if selected_id in valid_ids:
                break

            print("Invalid ID. Please choose one of the IDs shown above.")

        product = next(
            item for item in inventory
            if item["id"] == selected_id
        )

    else:
        product = matches[0]

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
        min_value=1
    )

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

        elif partner_share_mode == "custom_amount":
            partner_share_value = ask_float(
                "Partner share per unit ($): ",
                min_value=0
            )

            product["partner_share_mode"] = "custom_amount"
            product["partner_share_value"] = partner_share_value

    save_data(inventory, INVENTORY_FILE)

    print("Product updated successfully.")


def delete():
    inventory = load_data(INVENTORY_FILE)

    name = ask_text("Search for a product to delete: ")
    matches = []

    for product in inventory:
        if name.lower() in product["name"].lower():
            matches.append(product)

    if not matches:
        print("No products found.")
        return

    if len(matches) == 1:
        product_id = matches[0]["id"]

    else:
        print("Multiple products found:")

        for product in matches:
            print(f"ID: {product['id']} | Name: {product['name']}")

        valid_ids = [product["id"] for product in matches]

        while True:
            product_id = ask_int("Enter the ID of the product to delete: ")

            if product_id in valid_ids:
                break

            print("Invalid ID. Please choose one of the IDs shown above.")

    product = next(
        product for product in inventory
        if product["id"] == product_id
    )

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
    pass


def record_return():
    pass


def record_payment():
    pass


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