"""Writes sample_data/seed.sql: an invented reselling business for PSells'
sample stack, its AWS demonstration, its Kubernetes cluster and its tests.

    venv/bin/python sample_data/generate_seed.py

Nothing in it is real: the products, prices, dates, notes and the partner
percentage in sample_data/config.json are all made up. A fixed random seed
makes the output identical on every run, and tests/test_seed.py runs this
script and fails if seed.sql differs from what it writes, so the file is never
edited by hand.

It holds the invented records to the application's own rules rather than
restating them: every product is checked by psells.product_problems, the
rules the add form enforces, and every sale's frozen partner cut is
psells.partner_share_for's answer for its product, on the sample percentage.
Events are made in date order against a running count of what is available,
so no sale or return takes more than there is on its day, and every sale is
priced above its cut, so each makes a profit.

About 80 products in nine categories, sales over the twelve months to
September 2026 with a busier November and December, a few returns and monthly
payments to the partner, leaving a balance still owed. A handful of products
are written out by hand first, so every case the pages can show is present
whatever the random draw: the three partner-share modes, a product
discontinued at retail, glasses for a search to find, and one product out of
stock for each reason.
"""

import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_FILE = os.path.join(HERE, "seed.sql")

# The sample configuration's placeholder percentage, never the real one, for
# partner_share_for's default mode; set before psells is imported, since it
# reads the variable then.
os.environ["PSELLS_CONFIG"] = os.path.join(HERE, "config.json")
sys.path.insert(0, os.path.dirname(HERE))
import psells  # noqa: E402

RANDOM_SEED = 2026
FIRST_DAY = date(2025, 10, 1)
LAST_DAY = date(2026, 9, 30)
PRODUCTS = 80

CONDITIONS = ["Brand New", "Brand New", "Brand New", "Used (Like New)", "Used (Good)"]

# category: (retail price range in dollars, adjectives, things)
CATEGORIES = {
    "Watches": ((120, 450), ["Chrono Steel", "Field", "Minimal", "Diver", "Pilot", "Retro Digital"],
                ["Watch 40mm", "Watch 42mm", "Watch 38mm", "Watch on Leather", "Watch on Mesh"]),
    "Bags": ((40, 250), ["Canvas", "Leather", "Waxed", "Nylon", "Recycled"],
             ["Tote Bag", "Backpack 20L", "Crossbody Bag", "Weekender", "Laptop Sleeve 14in"]),
    "Hats": ((25, 60), ["Wool", "Canvas", "Corduroy", "Cotton", "Waxed"],
             ["Beanie", "Field Cap", "Bucket Hat", "Five-Panel Cap", "Flat Cap"]),
    "Glasses": ((30, 180), ["Polarised", "Blue Light", "Tortoise", "Wire Frame", "Clear"],
                ["Glasses Round Frame", "Sunglasses Matte Black", "Glasses Square Frame",
                 "Sunglasses Aviator"]),
    "Cups": ((20, 60), ["Insulated", "Ceramic", "Enamel", "Double-Wall", "Collapsible"],
             ["Travel Mug 500ml", "Coffee Cup 350ml", "Tumbler 600ml", "Camp Mug"]),
    "Shoes": ((60, 220), ["Trail", "Leather", "Canvas", "Knit", "Suede"],
              ["Runner", "Sneaker Low", "Chelsea Boot", "Loafer", "Hiking Shoe"]),
    "Jackets": ((80, 300), ["Down", "Rain", "Fleece", "Denim", "Softshell"],
                ["Jacket", "Parka", "Vest", "Overshirt", "Anorak"]),
    "Headphones": ((50, 350), ["Wireless", "Noise-Cancelling", "Studio", "Sport", "Compact"],
                   ["Headphones", "Earbuds", "On-Ear Headphones", "Neckband Earphones"]),
    "Wallets": ((30, 120), ["Leather", "Slim", "Canvas", "Card", "Zip"],
                ["Wallet", "Card Holder", "Bifold Wallet", "Coin Pouch"]),
}

RETURN_NOTES = ["unsold, sent back to the partner", "small scuff on the side",
                "print faded in the window", "missing its box", "stretched cuff",
                "box crushed in storage", "colour not selling"]
PAYMENT_NOTES = ["e-transfer", "e-transfer", "Cash"]


def dollars(rng, low, high, step=5):
    """A price in cents, a whole number of `step` dollars from low to high."""
    return rng.randrange(low // step, high // step + 1) * step * 100


def checked(product):
    """The product, after psells' own rules for a new product accept it."""
    problems = psells.product_problems(
        product["category"], product["name"], product["quantity_received"],
        product["retail_discontinued"], product["retail_price_cents"],
        product["listed_price_cents"], product["condition"],
        product["partner_share_mode"], product["partner_share_percent"],
        product["partner_share_amount_cents"])
    if problems:
        raise ValueError(f"invented product {product['name']!r}: {problems}")
    return product


def product(category, name, received, retail_cents, listed_cents, mode="default",
            percent=None, amount=None, discontinued=0, condition="Brand New", notes=""):
    return checked({
        "category": category, "name": name, "quantity_received": received,
        "retail_price_cents": retail_cents, "listed_price_cents": listed_cents,
        "retail_discontinued": discontinued, "partner_share_mode": mode,
        "partner_share_percent": percent, "partner_share_amount_cents": amount,
        "condition": condition, "notes": notes,
    })


def hand_written():
    """The cases every page must have something to show for, whatever the
    random draw, each with the events that make it so."""
    products = [
        product("Glasses", "Polarised Sunglasses Matte Black", 4, 16000, 11000,
                mode="custom_percent", percent=25.0),
        product("Glasses", "Blue Light Glasses Round Frame", 5, 3000, 2200),
        product("Watches", "Legacy Dive Watch", 2, 0, 18000, mode="custom_amount",
                amount=9000, discontinued=1, condition="Used (Good)",
                notes="no box, some scratches on the bezel"),
        product("Watches", "Trailrunner GPS Watch", 2, 30000, 22000,
                mode="custom_percent", percent=40.0, condition="Used (Like New)",
                notes="no box"),
        product("Bags", "Canvas Tote Bag Natural", 2, 4000, 2500),
        product("Hats", "Wool Beanie Charcoal", 3, 3500, 2500, mode="custom_amount",
                amount=800),
    ]
    # (product index, date, kind, quantity, sale price): the GPS watch sells
    # out, the tote goes back whole, the beanie is two sold and one returned,
    # and two sales share a date.
    events = [
        (3, date(2025, 11, 14), "sale", 1, 21000),
        (3, date(2026, 2, 3), "sale", 1, 21500),
        (4, date(2026, 3, 20), "return", 2, None),
        (5, date(2025, 12, 6), "sale", 2, 2400),
        (5, date(2026, 1, 17), "return", 1, None),
        (0, date(2026, 5, 9), "sale", 1, 10500),
        (2, date(2026, 5, 9), "sale", 1, 16500),
    ]
    return products, events


def random_products(rng, count):
    products = []
    names = set()
    while len(products) < count:
        category = rng.choice(list(CATEGORIES))
        (low, high), adjectives, things = CATEGORIES[category]
        name = f"{rng.choice(adjectives)} {rng.choice(things)}"
        if name in names:
            continue
        names.add(name)
        retail = dollars(rng, low, high)
        listed = round(retail * rng.uniform(0.6, 0.85) / 500) * 500
        mode = rng.choices(["default", "custom_percent", "custom_amount"],
                           weights=[6, 2, 2])[0]
        percent = amount = None
        if mode == "custom_percent":
            percent = float(rng.choice([20, 25, 30, 35]))
        elif mode == "custom_amount":
            amount = round(retail * rng.uniform(0.15, 0.3) / 100) * 100
        products.append(product(
            category, name, rng.choice([2, 3, 3, 4, 4, 5, 6, 8]), retail, listed,
            mode=mode, percent=percent, amount=amount,
            condition=rng.choice(CONDITIONS)))
    return products


def a_day(rng):
    """A day in the year, November and December twice as likely."""
    while True:
        day = FIRST_DAY + timedelta(days=rng.randrange((LAST_DAY - FIRST_DAY).days + 1))
        if day.month in (11, 12) or rng.random() < 0.5:
            return day


def random_events(rng, products, first_index):
    """Sales across the year, of whatever has stock, and a few returns."""
    events = []
    for _ in range(320):
        index = rng.randrange(first_index, len(products))
        listed = products[index]["listed_price_cents"]
        price = round(listed * rng.uniform(0.85, 1.05) / 100) * 100
        quantity = 2 if rng.random() < 0.08 else 1
        events.append((index, a_day(rng), "sale", quantity, price))
    # Many fall on something already sold out, or on a day with a return;
    # build() keeps a dozen of those that fit.
    for _ in range(40):
        events.append((rng.randrange(first_index, len(products)), a_day(rng),
                       "return", 1, None))
    return events


def build():
    rng = random.Random(RANDOM_SEED)
    products, events = hand_written()
    first_random = len(products)
    products += random_products(rng, PRODUCTS - len(products))
    events += random_events(rng, products, first_random)

    available = [p["quantity_received"] for p in products]
    sales, returns = [], []
    return_days = set()
    # Date order; on a day several share, the order they were made in, so the
    # hand-written events, made first, come first.
    ordered = [event for _, event in
               sorted(enumerate(events), key=lambda pair: (pair[1][1], pair[0]))]
    for index, day, kind, quantity, price in ordered:
        if quantity > available[index]:
            continue
        item = products[index]
        if kind == "sale":
            cut = psells.partner_share_for(item)
            if price <= cut:
                continue
            sales.append((day, index, quantity, price, cut))
        else:
            if day in return_days or len(returns) >= 12:
                continue
            return_days.add(day)
            returns.append((day, index, quantity, rng.choice(RETURN_NOTES)))
        available[index] -= quantity

    # Each month's payment is part of what the partner was owed by then, and
    # the last month is left owing.
    payments = []
    owed = 0
    month = FIRST_DAY
    while month <= LAST_DAY:
        owed += sum(q * cut for day, _, q, _, cut in sales
                    if (day.year, day.month) == (month.year, month.month))
        nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        if nxt <= LAST_DAY and owed > 0:
            amount = round(owed * rng.uniform(0.6, 0.9) / 1000) * 1000
            if amount:
                payments.append((nxt.replace(day=rng.randrange(3, 15)), amount,
                                 rng.choice(PAYMENT_NOTES)))
                owed -= amount
        month = nxt
    return products, sales, returns, payments


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, date):
        return quote(value.isoformat())
    return repr(value)


HEADER = """\
-- Invented sample records for PSells, in the current schema. Generated by
-- sample_data/generate_seed.py, which tests/test_seed.py runs to check this
-- file is exactly what it writes: change the script, never this file.
--
-- Apply to an empty database created from schema.sql. The README shows how,
-- in a Compose project of its own so it can never land in the real database.
--
-- Each INSERT names its id, so the rows reference each other the same way on
-- every run. Ids are GENERATED ALWAYS, which refuses an id supplied by an
-- INSERT unless it says OVERRIDING SYSTEM VALUE. The setval lines at the end
-- then move each sequence past the highest id.
--
-- None of this is real. The partner percentage in sample_data/config.json
-- is a placeholder too, and each sale's frozen cut is what that percentage,
-- or the product's own share, gives.
"""


def render(products, sales, returns, payments):
    lines = [HEADER, "BEGIN;", ""]
    for number, p in enumerate(products, start=1):
        values = [number, p["category"], p["name"], p["quantity_received"],
                  p["retail_price_cents"], p["listed_price_cents"],
                  p["retail_discontinued"], p["partner_share_mode"],
                  p["partner_share_percent"], p["partner_share_amount_cents"],
                  p["condition"], p["notes"]]
        lines.append("INSERT INTO products OVERRIDING SYSTEM VALUE VALUES ("
                     + ", ".join(sql(v) for v in values) + ");")
    lines.append("")
    for number, (day, index, quantity, price, cut) in enumerate(sales, start=1):
        lines.append("INSERT INTO sales OVERRIDING SYSTEM VALUE VALUES ("
                     + ", ".join(sql(v) for v in (number, day, index + 1, quantity,
                                                  price, cut)) + ");")
    lines.append("")
    for number, (day, index, quantity, notes) in enumerate(returns, start=1):
        lines.append("INSERT INTO returns OVERRIDING SYSTEM VALUE VALUES ("
                     + ", ".join(sql(v) for v in (number, day, index + 1, quantity,
                                                  notes)) + ");")
    lines.append("")
    for number, (day, amount, notes) in enumerate(payments, start=1):
        lines.append("INSERT INTO payments OVERRIDING SYSTEM VALUE VALUES ("
                     + ", ".join(sql(v) for v in (number, day, amount, notes)) + ");")
    lines.append("")
    for table in ("products", "sales", "returns", "payments"):
        lines.append(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                     f"(SELECT max(id) FROM {table}));")
    lines += ["", "COMMIT;", ""]
    return "\n".join(lines)


def main():
    text = render(*build())
    if "--check" in sys.argv:
        with open(SEED_FILE) as file:
            sys.exit(0 if file.read() == text else 1)
    with open(SEED_FILE, "w") as file:
        file.write(text)


if __name__ == "__main__":
    main()
