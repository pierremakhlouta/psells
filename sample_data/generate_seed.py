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

Then seven items at every stage of the workflow, after all of those so
nothing above them changes: received, researched (one not worth listing),
photographed, and listed (one on Instagram, one not selling). Their dates are
written as days before the day the seed is loaded, so after every nightly
reset of the demo they have waited the same number of days. The older
products have no arrival or listing date, like the real ones from before the
workflow. Their photos are plain invented pictures this script writes into
sample_data/photos, checked like seed.sql.
"""

import io
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

CONDITIONS = ["Brand new", "Brand new", "Brand new", "Like new", "Used"]

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

# The conditions every database starts with (schema.sql inserts the same),
# listed again so a reset that emptied them puts them back.
CONDITION_LIST = ["Brand new", "Open box", "Like new", "Used", "Damaged"]

# An invented pair of listing templates, in the shape of the real ones, which
# live only in the business's own database.
TEMPLATES = {
    "facebook": ("{name}.\n\nRetail price: {retail}\nMy price: {price}\n\n"
                 "Condition: {condition}.\n\n{details}\n\n"
                 "Pickup at the invented station."),
    "instagram": ("Sample deal: {name}\n\nPrice: {price}\nRetail: {retail}\n\n"
                  "Condition: {condition}\n\n{details}\n\n"
                  "Pickup at the invented station.\n\n#SampleDeals"),
}


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
            percent=None, amount=None, discontinued=0, condition="Brand new", notes=""):
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
                amount=9000, discontinued=1, condition="Used",
                notes="no box, some scratches on the bezel"),
        product("Watches", "Trailrunner GPS Watch", 2, 30000, 22000,
                mode="custom_percent", percent=40.0, condition="Like new",
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


class DaysAgo:
    """A date written as so many days before the day the seed is loaded, so
    the workflow's items wait the same number of days after every nightly
    reset of the demo, rather than ageing past every limit."""

    def __init__(self, days):
        self.days = days


def workflow_items():
    """One or more invented items at every stage of the workflow, with the
    dates and photos that put them there, added after every other product so
    nothing above them changes: (product, arrived days ago, listed days ago
    or None, photo count)."""
    def item(category, name, received, retail, listed, condition, marketplace,
             details="", on_instagram=False, mode="default", amount=None):
        made = product(category, name, received, retail, listed, mode=mode,
                       amount=amount, condition=condition)
        made.update({"marketplace_price_cents": marketplace, "details": details,
                     "on_instagram": on_instagram})
        return made

    return [
        # Received: nothing known yet but what it is and how many.
        (item("Cups", "Insulated Camp Mug Olive", 3, None, None, None, None), 2, None, 0),
        (item("Hats", "Corduroy Bucket Hat Rust", 1, None, None, None, None), 6, None, 0),
        # Researched, and one of them not worth listing: a $40.00 retail price
        # pays the partner $12.00, leaving $13.00 at a $25.00 Marketplace price.
        (item("Wallets", "Slim Card Holder Tan", 2, 4500, None, "Brand new", 3500), 9, None, 0),
        (item("Cups", "Enamel Camp Mug Speckled", 2, 4000, None, "Open box", 2500), 11, None, 0),
        # Photographed.
        (item("Bags", "Waxed Crossbody Bag Brown", 1, 12000, None, "Like new", 9000,
              details="Adjustable strap"), 14, None, 2),
        # Listed: one recently, and on Instagram too; one long enough to be
        # flagged as not selling.
        (item("Headphones", "Compact Earbuds White", 4, 9000, 6500, "Brand new", 7000,
              details="Charging case and three tip sizes", on_instagram=True), 20, 5, 2),
        (item("Jackets", "Fleece Vest Grey", 1, 7500, 5000, "Used", 5500,
              details="Small mark on the hem"), 60, 45, 1),
    ]


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
    # The workflow's items last: no sales, so nothing above them moves.
    photos = []
    for item, arrived, listed_days, photo_count in workflow_items():
        item["arrived_on"] = DaysAgo(arrived)
        item["listed_on"] = None if listed_days is None else DaysAgo(listed_days)
        products.append(item)
        for _ in range(photo_count):
            photos.append((len(products), f"sample-{len(photos) + 1}.jpg"))
    return products, sales, returns, payments, photos


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def sql(value):
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return quote(value)
    if isinstance(value, date):
        return quote(value.isoformat())
    if isinstance(value, DaysAgo):
        return f"CURRENT_DATE - {value.days}"
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
-- The category and condition lists and the two listing templates come first.
-- Each is written to change nothing if it is already there, so the demo's
-- nightly reset can load this file again after emptying the records.
--
-- None of this is real. The partner percentage in sample_data/config.json
-- is a placeholder too, and each sale's frozen cut is what that percentage,
-- or the product's own share, gives.
"""


PRODUCT_COLUMNS = ("id", "category", "name", "quantity_received",
                   "retail_price_cents", "listed_price_cents",
                   "retail_discontinued", "partner_share_mode",
                   "partner_share_percent", "partner_share_amount_cents",
                   "condition", "notes", "marketplace_price_cents", "details",
                   "on_instagram", "arrived_on", "listed_on")


def render(products, sales, returns, payments, photos):
    lines = [HEADER, "BEGIN;", ""]
    for name in sorted({p["category"] for p in products}):
        lines.append(f"INSERT INTO categories (name) VALUES ({sql(name)}) "
                     "ON CONFLICT DO NOTHING;")
    for position, name in enumerate(CONDITION_LIST, start=1):
        lines.append(f"INSERT INTO conditions (name, position) VALUES ({sql(name)}, "
                     f"{position}) ON CONFLICT DO NOTHING;")
    for platform, body in TEMPLATES.items():
        lines.append(f"INSERT INTO listing_templates (platform, body) VALUES "
                     f"({sql(platform)}, {sql(body)}) "
                     "ON CONFLICT (platform) DO UPDATE SET body = EXCLUDED.body;")
    lines.append("")
    # The columns named, so a product from before the workflow gets no
    # arrival date rather than the column's default of the day it is loaded.
    for number, p in enumerate(products, start=1):
        row = {"id": number, "marketplace_price_cents": None, "details": "",
               "on_instagram": False, "arrived_on": None, "listed_on": None, **p}
        lines.append(f"INSERT INTO products ({', '.join(PRODUCT_COLUMNS)}) "
                     "OVERRIDING SYSTEM VALUE VALUES ("
                     + ", ".join(sql(row[column]) for column in PRODUCT_COLUMNS)
                     + ");")
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
    for number, (product_id, file_name) in enumerate(photos, start=1):
        lines.append("INSERT INTO photos (id, product_id, file_name) "
                     "OVERRIDING SYSTEM VALUE VALUES ("
                     + ", ".join(sql(v) for v in (number, product_id, file_name))
                     + ");")
    lines.append("")
    for table in ("products", "sales", "returns", "payments", "photos"):
        lines.append(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                     f"(SELECT max(id) FROM {table}));")
    lines += ["", "COMMIT;", ""]
    return "\n".join(lines)


PHOTO_DIR = os.path.join(HERE, "photos")
PHOTO_COLOURS = [(70, 110, 160), (150, 90, 60), (90, 140, 90), (160, 140, 70),
                 (120, 90, 150)]


def placeholder(number):
    """A plain invented picture for sample photo `number`: a coloured field
    with a lighter panel, labelled, 800 by 600. Pillow writes the same bytes
    for the same picture, so the file can be checked like seed.sql."""
    from PIL import Image, ImageDraw

    colour = PHOTO_COLOURS[(number - 1) % len(PHOTO_COLOURS)]
    image = Image.new("RGB", (800, 600), colour)
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 150, 600, 450), fill=tuple(min(255, c + 70) for c in colour))
    draw.text((330, 290), f"Sample photo {number}", fill=(255, 255, 255))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=80)
    return out.getvalue()


def main():
    built = build()
    text = render(*built)
    photos = {name: placeholder(number)
              for number, (_, name) in enumerate(built[4], start=1)}
    if "--check" in sys.argv:
        with open(SEED_FILE) as file:
            same = file.read() == text
        on_disk = sorted(os.listdir(PHOTO_DIR)) if os.path.isdir(PHOTO_DIR) else []
        same = same and on_disk == sorted(photos)
        for name, data in photos.items():
            if same:
                with open(os.path.join(PHOTO_DIR, name), "rb") as file:
                    same = file.read() == data
        sys.exit(0 if same else 1)
    with open(SEED_FILE, "w") as file:
        file.write(text)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    for name in os.listdir(PHOTO_DIR):
        os.remove(os.path.join(PHOTO_DIR, name))
    for name, data in photos.items():
        with open(os.path.join(PHOTO_DIR, name), "wb") as file:
            file.write(data)


if __name__ == "__main__":
    main()
