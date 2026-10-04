"""Tests for schema_postgres.sql, run against a real PostgreSQL.

Each rule the schema carries is tried with a row that breaks exactly that
rule, and the refusal must name the constraint that was meant to catch it. A
test that accepted any refusal would pass for the wrong reason: a row broken in
two ways is refused by whichever check runs first.

The control test matters as much as the refusals. Every bad row is the good
row with one field changed, so the good row being accepted is what shows each
refusal is about that one field.
"""

import datetime
import os

import psycopg
import pytest
from psycopg import errors

from helpers import TEST_DATABASE_URL


GOOD_PRODUCT = {
    "category": "Watches",
    "name": "Field Watch",
    "quantity_received": 3,
    "retail_price_cents": 20000,
    "listed_price_cents": 14000,
    "retail_discontinued": 0,
    "partner_share_mode": "default",
    "partner_share_percent": None,
    "partner_share_amount_cents": None,
    "condition": "Brand New",
    "notes": "",
}


def insert_product(db, **changes):
    row = GOOD_PRODUCT | changes
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    return db.execute(
        f"INSERT INTO products ({columns}) VALUES ({placeholders}) RETURNING id",
        list(row.values()),
    ).fetchone()["id"]


def insert_sale(db, item_id, quantity=1, date="2026-05-14",
                sale_price_cents=15000, partner_share_cents=6000):
    return db.execute(
        "INSERT INTO sales (date, item_id, quantity, sale_price_cents, "
        "partner_share_cents) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (date, item_id, quantity, sale_price_cents, partner_share_cents),
    ).fetchone()["id"]


def insert_return(db, item_id, quantity=1, date="2026-06-30"):
    return db.execute(
        "INSERT INTO returns (date, item_id, quantity, notes) "
        "VALUES (%s, %s, %s, '') RETURNING id",
        (date, item_id, quantity),
    ).fetchone()["id"]


def refused(db, statement, parameters=()):
    """Run a statement that must fail, and hand back the error it raised."""
    with pytest.raises(errors.IntegrityError) as caught:
        with db.transaction():
            db.execute(statement, parameters)
    return caught.value


# Products --------------------------------------------------------------------

def test_the_good_product_is_accepted(db):
    product_id = insert_product(db)

    row = db.execute("SELECT * FROM products WHERE id = %s",
                     (product_id,)).fetchone()
    assert row["name"] == "Field Watch"


@pytest.mark.parametrize("changes, constraint", [
    ({"category": "   "}, "products_category_check"),
    ({"name": ""}, "products_name_check"),
    ({"quantity_received": 0}, "products_quantity_received_check"),
    ({"retail_price_cents": -1}, "products_retail_price_cents_check"),
    ({"listed_price_cents": -1}, "products_listed_price_cents_check"),
    ({"retail_discontinued": 2}, "products_retail_discontinued_check"),
    ({"condition": " "}, "products_condition_check"),
    ({"partner_share_mode": "custom_amount",
      "partner_share_amount_cents": -1},
     "products_partner_share_amount_cents_check"),
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": 100.5},
     "products_partner_share_percent_check"),
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": -0.5},
     "products_partner_share_percent_check"),
    # PostgreSQL sorts NaN above every number, so the range refuses it.
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": float("nan")},
     "products_partner_share_percent_check"),
    ({"partner_share_mode": "custom_percent",
      "partner_share_percent": float("inf")},
     "products_partner_share_percent_check"),
    # Each mode allows exactly one shape.
    ({"partner_share_percent": 40.0}, "partner_share_matrix"),
    ({"partner_share_amount_cents": 500}, "partner_share_matrix"),
    ({"partner_share_mode": "custom_percent"}, "partner_share_matrix"),
    ({"partner_share_mode": "custom_amount"}, "partner_share_matrix"),
    ({"partner_share_mode": "custom_amount",
      "partner_share_amount_cents": 500,
      "partner_share_percent": 40.0}, "partner_share_matrix"),
    # A discontinued product has no retail price and a fixed partner amount;
    # a current one has a retail price.
    ({"retail_price_cents": 0}, "retail_discontinued_rules"),
    ({"retail_discontinued": 1, "partner_share_mode": "custom_amount",
      "partner_share_amount_cents": 500}, "retail_discontinued_rules"),
    ({"retail_discontinued": 1, "retail_price_cents": 0},
     "retail_discontinued_rules"),
])
def test_a_product_breaking_one_rule_is_refused_by_that_rule(
        db, changes, constraint):
    row = GOOD_PRODUCT | changes

    error = refused(
        db,
        f"INSERT INTO products ({', '.join(row)}) "
        f"VALUES ({', '.join(['%s'] * len(row))})",
        list(row.values()),
    )

    assert error.diag.constraint_name == constraint


def test_an_unknown_partner_share_mode_is_refused(db):
    # No row can pass partner_share_matrix with an unknown mode, so which of
    # the two constraints reports it is PostgreSQL's choice. Either is right.
    row = GOOD_PRODUCT | {"partner_share_mode": "sometimes"}

    error = refused(
        db,
        f"INSERT INTO products ({', '.join(row)}) "
        f"VALUES ({', '.join(['%s'] * len(row))})",
        list(row.values()),
    )

    assert error.diag.constraint_name in (
        "partner_share_mode_valid", "partner_share_matrix")


@pytest.mark.parametrize("column", [
    "category", "name", "quantity_received", "retail_price_cents",
    "listed_price_cents", "retail_discontinued", "partner_share_mode",
    "condition", "notes",
])
def test_a_required_product_column_cannot_be_null(db, column):
    row = GOOD_PRODUCT | {column: None}

    with pytest.raises(errors.NotNullViolation):
        with db.transaction():
            insert_product(db, **row)


def test_a_discontinued_product_with_a_fixed_amount_is_accepted(db):
    product_id = insert_product(
        db, retail_discontinued=1, retail_price_cents=0,
        partner_share_mode="custom_amount", partner_share_amount_cents=9000)

    assert product_id > 0


def test_money_beyond_an_integer_is_refused_rather_than_wrapped(db):
    with pytest.raises(errors.NumericValueOutOfRange):
        with db.transaction():
            insert_product(db, retail_price_cents=2**31)


# Ids -------------------------------------------------------------------------

def test_an_insert_cannot_choose_its_own_id(db):
    row = GOOD_PRODUCT | {"id": 999}

    with pytest.raises(errors.GeneratedAlways):
        with db.transaction():
            db.execute(
                f"INSERT INTO products ({', '.join(row)}) "
                f"VALUES ({', '.join(['%s'] * len(row))})",
                list(row.values()),
            )


def test_an_id_is_never_reused_after_the_newest_product_is_deleted(db):
    deleted = insert_product(db, name="Deleted")
    db.execute("DELETE FROM products WHERE id = %s", (deleted,))

    added_after = insert_product(db, name="Added after")

    assert added_after > deleted


# Sales, returns and payments -------------------------------------------------

@pytest.mark.parametrize("changes, constraint", [
    ({"quantity": 0}, "sales_quantity_check"),
    ({"sale_price_cents": -1}, "sales_sale_price_cents_check"),
    ({"partner_share_cents": -1}, "sales_partner_share_cents_check"),
])
def test_a_sale_breaking_one_rule_is_refused_by_that_rule(
        db, changes, constraint):
    product_id = insert_product(db)

    with pytest.raises(errors.CheckViolation) as caught:
        with db.transaction():
            insert_sale(db, product_id, **changes)

    assert caught.value.diag.constraint_name == constraint


def test_a_return_of_no_units_is_refused(db):
    product_id = insert_product(db)

    with pytest.raises(errors.CheckViolation) as caught:
        with db.transaction():
            insert_return(db, product_id, quantity=0)

    assert caught.value.diag.constraint_name == "returns_quantity_check"


def test_a_negative_payment_is_refused(db):
    error = refused(
        db,
        "INSERT INTO payments (date, amount_cents, notes) "
        "VALUES ('2026-06-05', -1, '')",
    )

    assert error.diag.constraint_name == "payments_amount_cents_check"


@pytest.mark.parametrize("table, statement", [
    ("sales",
     "INSERT INTO sales (date, item_id, quantity, sale_price_cents, "
     "partner_share_cents) VALUES ('2026-05-14', %s, 1, 100, 40)"),
    ("returns",
     "INSERT INTO returns (date, item_id, quantity, notes) "
     "VALUES ('2026-05-14', %s, 1, '')"),
])
def test_a_row_for_a_product_that_does_not_exist_is_refused(
        db, table, statement):
    missing = insert_product(db)
    db.execute("DELETE FROM products WHERE id = %s", (missing,))

    error = refused(db, statement, (missing,))

    assert isinstance(error, errors.ForeignKeyViolation)
    assert error.diag.constraint_name == f"{table}_item_id_fkey"


@pytest.mark.parametrize("record, table", [
    (insert_sale, "sales"),
    (insert_return, "returns"),
])
def test_a_product_with_history_cannot_be_deleted(db, record, table):
    product_id = insert_product(db)
    record(db, product_id)

    error = refused(db, "DELETE FROM products WHERE id = %s", (product_id,))

    # The class of error depends on the version: PostgreSQL 18 reports ON
    # DELETE RESTRICT as RestrictViolation, 16 as ForeignKeyViolation. Both
    # are integrity errors, and both name the key that refused, which is what
    # the rule is about.
    assert error.diag.constraint_name == f"{table}_item_id_fkey"


@pytest.mark.parametrize("text", ["2026-02-30", "2026-13-01", "not a date"])
def test_an_impossible_date_is_refused_by_the_type(db, text):
    product_id = insert_product(db)

    with pytest.raises(errors.DataError):
        with db.transaction():
            insert_sale(db, product_id, date=text)


def test_a_date_is_stored_as_a_date_whatever_its_padding(db):
    # SQLite checked text, so 2026-9-3 was refused and create_sale had to pad
    # it (31.4). The DATE type stores a day, not the characters it was
    # written with.
    product_id = insert_product(db)
    sale_id = insert_sale(db, product_id, date="2026-9-3")

    stored = db.execute("SELECT date FROM sales WHERE id = %s",
                        (sale_id,)).fetchone()["date"]

    assert stored == datetime.date(2026, 9, 3)


# The view and the types Python receives --------------------------------------

def test_the_view_derives_stock_without_multiplying_sales_by_returns(db):
    # Two sales and three returns: joined naively they would make six rows
    # and every sum would be wrong.
    product_id = insert_product(db, quantity_received=10)
    insert_sale(db, product_id, quantity=2)
    insert_sale(db, product_id, quantity=1)
    insert_return(db, product_id, quantity=1)
    insert_return(db, product_id, quantity=1)
    insert_return(db, product_id, quantity=2)

    rows = db.execute("SELECT * FROM products_view WHERE id = %s",
                      (product_id,)).fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row["quantity_sold"] == 3
    assert row["quantity_returned"] == 4
    assert row["quantity_available"] == 3


def test_a_product_with_no_history_shows_zero_not_null(db):
    product_id = insert_product(db)

    row = db.execute("SELECT * FROM products_view WHERE id = %s",
                     (product_id,)).fetchone()

    assert (row["quantity_sold"], row["quantity_returned"],
            row["quantity_available"]) == (0, 0, 3)


def test_python_receives_the_types_the_application_expects(db):
    # A third: a percentage whose float needs all of its digits.
    percent = 100 / 3
    product_id = insert_product(db, partner_share_mode="custom_percent",
                                partner_share_percent=percent)
    insert_sale(db, product_id)

    product = db.execute("SELECT * FROM products_view WHERE id = %s",
                         (product_id,)).fetchone()
    revenue = db.execute(
        "SELECT COALESCE(SUM(quantity * sale_price_cents), 0) AS total "
        "FROM sales").fetchone()["total"]
    sale_date = db.execute("SELECT date FROM sales").fetchone()["date"]

    # A percentage reads back as exactly the float that went in, as SQLite's
    # REAL did. PostgreSQL's four-byte real keeps about seven significant
    # digits and would give back 33.333332. A short value such as 12.3 would
    # not show the difference, which is why this one is long.
    assert type(product["partner_share_percent"]) is float
    assert product["partner_share_percent"] == percent
    # Money and quantities are int, sums included. A bigint column would sum
    # to Decimal.
    assert type(product["retail_price_cents"]) is int
    assert type(product["quantity_available"]) is int
    assert type(revenue) is int
    assert type(product["retail_discontinued"]) is int
    assert type(sale_date) is datetime.date


# Authentication --------------------------------------------------------------
#
# The users and sessions tables of Phase 05b. A stand-in Argon2id string is
# enough here: the table checks the prefix, not the hash.

GOOD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2g"
NOW = datetime.datetime(2026, 9, 27, 10, 0, tzinfo=datetime.timezone.utc)


def insert_user(db, username="owner", password_hash=GOOD_HASH):
    return db.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s, %s) "
        "RETURNING id",
        (username, password_hash),
    ).fetchone()["id"]


def insert_session(db, user_id, token_digest=b"\x01" * 32,
                   form_token="f" * 43, created_at=NOW, last_seen_at=NOW):
    db.execute(
        "INSERT INTO sessions (token_digest, user_id, form_token, created_at, "
        "last_seen_at) VALUES (%s, %s, %s, %s, %s)",
        (token_digest, user_id, form_token, created_at, last_seen_at),
    )


def test_the_good_user_and_session_are_accepted(db):
    user_id = insert_user(db)
    insert_session(db, user_id)

    row = db.execute("SELECT * FROM sessions").fetchone()
    assert row["user_id"] == user_id
    assert row["created_at"] == NOW


@pytest.mark.parametrize("username, password_hash, constraint", [
    ("", GOOD_HASH, "users_username_check"),
    (" owner", GOOD_HASH, "users_username_check"),
    ("owner ", GOOD_HASH, "users_username_check"),
    # A plain password, and Argon2's other two variants, are all refused.
    ("owner", "correct horse battery staple", "users_password_hash_check"),
    ("owner", GOOD_HASH.replace("argon2id", "argon2i"),
     "users_password_hash_check"),
    ("owner", GOOD_HASH.replace("argon2id", "argon2d"),
     "users_password_hash_check"),
])
def test_a_user_breaking_one_rule_is_refused_by_that_rule(
        db, username, password_hash, constraint):
    error = refused(
        db,
        "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
        (username, password_hash),
    )

    assert error.diag.constraint_name == constraint


def test_two_users_cannot_share_a_username(db):
    insert_user(db)

    error = refused(
        db,
        "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
        ("owner", GOOD_HASH),
    )

    assert isinstance(error, errors.UniqueViolation)
    assert error.diag.constraint_name == "users_username_key"


@pytest.mark.parametrize("changes, constraint", [
    ({"token_digest": b"\x01" * 31}, "sessions_token_digest_check"),
    ({"token_digest": b"\x01" * 33}, "sessions_token_digest_check"),
    ({"form_token": "f" * 31}, "sessions_form_token_check"),
    ({"last_seen_at": NOW - datetime.timedelta(seconds=1)},
     "session_times_in_order"),
])
def test_a_session_breaking_one_rule_is_refused_by_that_rule(
        db, changes, constraint):
    user_id = insert_user(db)

    with pytest.raises(errors.IntegrityError) as caught:
        with db.transaction():
            insert_session(db, user_id, **changes)

    assert caught.value.diag.constraint_name == constraint


def test_a_session_for_a_user_that_does_not_exist_is_refused(db):
    missing = insert_user(db)
    db.execute("DELETE FROM users WHERE id = %s", (missing,))

    with pytest.raises(errors.ForeignKeyViolation) as caught:
        with db.transaction():
            insert_session(db, missing)

    assert caught.value.diag.constraint_name == "sessions_user_id_fkey"


def test_deleting_a_user_ends_their_sessions(db):
    user_id = insert_user(db)
    insert_session(db, user_id, token_digest=b"\x01" * 32)
    insert_session(db, user_id, token_digest=b"\x02" * 32)

    db.execute("DELETE FROM users WHERE id = %s", (user_id,))

    count = db.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
    assert count["n"] == 0


# The corrections log ---------------------------------------------------------

def insert_correction(db, **changes):
    values = {"record_type": "sale", "record_id": 1, "action": "edit",
              "before": '{"quantity": 2}', "after": '{"quantity": 1}'}
    values.update(changes)
    return db.execute(
        "INSERT INTO corrections (record_type, record_id, action, before, "
        "after) VALUES (%(record_type)s, %(record_id)s, %(action)s, "
        "%(before)s, %(after)s) RETURNING *",
        values,
    ).fetchone()


def test_a_good_edit_and_a_good_delete_are_logged(db):
    edited = insert_correction(db)
    deleted = insert_correction(db, record_type="payment", action="delete",
                                after=None)

    assert edited["before"] == {"quantity": 2}
    assert edited["after"] == {"quantity": 1}
    assert deleted["after"] is None
    assert edited["at"] is not None


@pytest.mark.parametrize("changes, constraint", [
    ({"record_type": "product"}, "corrections_record_type_check"),
    ({"action": "undo", "after": None}, "corrections_action_check"),
    ({"action": "edit", "after": None}, "after_only_for_an_edit"),
    ({"action": "delete"}, "after_only_for_an_edit"),
])
def test_a_correction_breaking_one_rule_is_refused_by_that_rule(
        db, changes, constraint):
    with pytest.raises(errors.IntegrityError) as caught:
        with db.transaction():
            insert_correction(db, **changes)

    assert caught.value.diag.constraint_name == constraint


def test_a_correction_needs_its_before(db):
    with pytest.raises(errors.NotNullViolation):
        with db.transaction():
            insert_correction(db, before=None)


@pytest.mark.parametrize("statement", [
    "UPDATE corrections SET record_id = 2",
    "DELETE FROM corrections",
])
def test_a_logged_correction_can_never_be_changed_or_removed(db, statement):
    insert_correction(db)

    with pytest.raises(errors.RaiseException) as caught:
        with db.transaction():
            db.execute(statement)

    assert "append-only" in str(caught.value)
    assert db.execute("SELECT count(*) AS n FROM corrections").fetchone()[
        "n"] == 1


# The migrations ------------------------------------------------------------------
#
# A database made before a table was added gets it from a file in
# migrations/, and a new one from the end of schema.sql. Both must end up the
# same, or the live database and every fresh one (the tests, the sample stack,
# a rebuild from a backup's schema) quietly differ.
#
# Each is built in a schema of its own inside the test's transaction, so the
# rollback removes both. The oldest database is schema.sql up to the first
# migration's heading, with every migration then applied in order, which is why
# each migration's section sits at the end of schema.sql, in the same order.

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Each migration, with the heading of its section in schema.sql.
MIGRATIONS = [
    ("0001_authentication.sql", "-- Authentication ---"),
    ("0002_corrections.sql", "-- Corrections ---"),
]


def read(*path):
    with open(os.path.join(HERE, *path)) as source:
        return source.read()


def describe(db, schema):
    """Every column, constraint, index and view in one schema, as plain text.

    search_path is set to the schema being described, so the definitions
    PostgreSQL prints name its tables without a schema in front, and the two
    descriptions can be compared as they are.
    """
    db.execute(f"SET LOCAL search_path TO {schema}")

    columns = db.execute(
        "SELECT table_name, column_name, data_type, is_nullable, "
        "column_default, is_identity, identity_generation "
        "FROM information_schema.columns WHERE table_schema = %s "
        "ORDER BY table_name, column_name",
        (schema,),
    ).fetchall()
    constraints = db.execute(
        "SELECT c.conrelid::regclass::text AS table_name, c.conname, "
        "pg_get_constraintdef(c.oid) AS definition "
        "FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = %s ORDER BY 1, 2",
        (schema,),
    ).fetchall()
    indexes = db.execute(
        "SELECT indexname, replace(indexdef, %s, '') AS definition "
        "FROM pg_indexes WHERE schemaname = %s ORDER BY 1",
        (f"{schema}.", schema),
    ).fetchall()
    views = db.execute(
        "SELECT viewname, definition FROM pg_views "
        "WHERE schemaname = %s ORDER BY 1",
        (schema,),
    ).fetchall()
    functions = db.execute(
        "SELECT p.proname, p.prosrc FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = %s ORDER BY 1",
        (schema,),
    ).fetchall()
    triggers = db.execute(
        "SELECT t.tgname, replace(pg_get_triggerdef(t.oid), %s, '') "
        "AS definition "
        "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND NOT t.tgisinternal ORDER BY 1",
        (f"{schema}.", schema),
    ).fetchall()

    return columns, constraints, indexes, views, functions, triggers


def test_every_migration_is_listed_and_its_section_is_in_order():
    schema = read("schema.sql")
    positions = []
    for _, heading in MIGRATIONS:
        assert schema.count(heading) == 1, heading
        positions.append(schema.index(heading))

    assert positions == sorted(positions)
    assert sorted(os.listdir(os.path.join(HERE, "migrations"))) == [
        name for name, _ in MIGRATIONS]


def test_the_migrations_build_what_schema_sql_builds(db):
    schema = read("schema.sql")
    before_migrations = schema.split(MIGRATIONS[0][1])[0]

    db.execute("CREATE SCHEMA fresh")
    db.execute("SET LOCAL search_path TO fresh")
    db.execute(schema)

    db.execute("CREATE SCHEMA migrated")
    db.execute("SET LOCAL search_path TO migrated")
    db.execute(before_migrations)
    for name, _ in MIGRATIONS:
        db.execute(read("migrations", name))

    fresh = describe(db, "fresh")
    migrated = describe(db, "migrated")
    db.execute("SET LOCAL search_path TO public")

    # Not empty, so two empty descriptions cannot pass as equal.
    assert any(row["table_name"] == "sessions" for row in fresh[0])
    assert any(row["table_name"] == "corrections" for row in fresh[0])
    assert [row["tgname"] for row in fresh[5]] == ["corrections_append_only"]
    assert fresh == migrated


@pytest.mark.parametrize("name", [name for name, _ in MIGRATIONS])
def test_a_migration_has_no_transaction_of_its_own(name):
    # psql's --single-transaction supplies one. A COMMIT in the file would end
    # the test's transaction above and leave its schemas behind, and a BEGIN
    # would only draw a warning from psql. A function body between $$ marks
    # has a BEGIN of its own, which is PL/pgSQL's and not a transaction.
    outside_bodies = "".join(read("migrations", name).split("$$")[::2])
    statements = [
        line.strip().upper()
        for line in outside_bodies.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]

    assert not any(line.startswith(("BEGIN", "COMMIT", "ROLLBACK"))
                   for line in statements)


# Isolation -------------------------------------------------------------------

def test_a_transaction_block_in_a_test_does_not_commit(db):
    # db.transaction() commits when it opens a transaction of its own, and is
    # a savepoint only inside one that is already open. The fixture opens one
    # first so that a block like this, even as a test's first statement, can
    # never commit. A second connection sees only what was committed.
    with db.transaction():
        db.execute("INSERT INTO payments (date, amount_cents, notes) "
                   "VALUES ('2026-06-05', 100, 'must not be committed')")

    with psycopg.connect(TEST_DATABASE_URL) as other:
        seen = other.execute(
            "SELECT COUNT(*) FROM payments "
            "WHERE notes = 'must not be committed'").fetchone()[0]

    assert seen == 0


def test_every_test_starts_with_empty_tables(db):
    # Last in the file on purpose: every test above has written rows, and each
    # one's rollback is what leaves these tables empty. If the fixture ever
    # committed instead, this is the test that would say so.
    for table in ("products", "sales", "returns", "payments",
                  "users", "sessions", "corrections"):
        count = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        assert count["n"] == 0, table
