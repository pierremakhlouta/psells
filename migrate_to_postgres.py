"""One-time move of the PSells records from SQLite into PostgreSQL.

Run once, in Phase 04, inside a one-off container of the app service, because
the real database publishes no port. The README's "Moving from SQLite" section
has the command. It reads a copy of the SQLite file, never the live one, and
opens it read-only.

Every row is copied with its id, so sales and returns keep pointing at the
products they always pointed at, and each table's sequence is then moved past
its highest id so the next record added gets a new one.

Everything happens in one transaction, and nothing is committed until the
result has been checked against the source: every row and every column, the
three derived quantities of every product, all nine dashboard figures, and
every product's partner cut, each worked out by the same psells functions on
both sides. Money is whole cents on both sides, so the comparison is exact,
not within a tolerance. Any difference raises MigrationError, the transaction
rolls back, and the database is left as empty as it was found.

It refuses a target that already holds records rather than merging into it,
and a source that fails SQLite's own integrity or foreign key checks.

It prints counts and a verdict, never a figure, so its output can be kept.
"""

import os
import sqlite3
import sys
from datetime import date

import psycopg

import psells


# Every column of every table, in the order both schemas declare them, and the
# order the tables are loaded in: products before the sales and returns that
# point at them.
TABLES = {
    "products": (
        "id", "category", "name", "quantity_received", "retail_price_cents",
        "listed_price_cents", "retail_discontinued", "partner_share_mode",
        "partner_share_percent", "partner_share_amount_cents", "condition",
        "notes",
    ),
    "sales": (
        "id", "date", "item_id", "quantity", "sale_price_cents",
        "partner_share_cents",
    ),
    "returns": ("id", "date", "item_id", "quantity", "notes"),
    "payments": ("id", "date", "amount_cents", "notes"),
}

DERIVED = ("quantity_sold", "quantity_returned", "quantity_available")


class MigrationError(Exception):
    """The migration was refused or did not check out; nothing was kept."""


def open_source(path):
    """The SQLite file, opened read-only, with rows readable by name.

    mode=ro makes a write through this connection an error, and it also stops
    sqlite3.connect from quietly creating an empty database when the path is
    wrong, which is what it does by default.
    """
    if not os.path.isfile(path):
        raise MigrationError(f"No SQLite file at {path}")

    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    return source


def check_source(source):
    """Refuse a source SQLite itself does not trust."""
    verdict = source.execute("PRAGMA integrity_check").fetchone()[0]
    if verdict != "ok":
        raise MigrationError(f"The SQLite file fails its integrity check: "
                             f"{verdict}")

    orphans = source.execute("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise MigrationError(f"The SQLite file has {len(orphans)} row(s) "
                             f"pointing at a product that does not exist")


def source_rows(source, table):
    """Every row of one source table, in id order, as PostgreSQL will hold it.

    The one conversion: SQLite kept dates as text, which the schema checked
    was a real date, and PostgreSQL keeps them as dates.
    """
    columns = TABLES[table]
    rows = []
    for row in source.execute(
            f"SELECT {', '.join(columns)} FROM {table} ORDER BY id"):
        values = dict(row)
        if "date" in values:
            values["date"] = date.fromisoformat(values["date"])
        rows.append(values)
    return rows


def target_rows(target, table):
    columns = TABLES[table]
    return [dict(row) for row in target.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY id")]


def load(target, table, rows):
    """Insert rows with their own ids, then move the sequence past them.

    OVERRIDING SYSTEM VALUE because the ids are GENERATED ALWAYS. setval's
    third argument says whether the value given has been used: with rows, the
    highest id has, so the next is one more; with none, the next is 1.
    """
    columns = TABLES[table]
    if rows:
        with target.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"OVERRIDING SYSTEM VALUE "
                f"VALUES ({', '.join(['%s'] * len(columns))})",
                [tuple(row[column] for column in columns) for row in rows],
            )

    target.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
        f"COALESCE((SELECT max(id) FROM {table}), 1), "
        f"(SELECT count(*) > 0 FROM {table}))"
    )


def derived_quantities(connection):
    """Each product's three derived quantities, from that database's view."""
    return {
        row["id"]: tuple(row[column] for column in DERIVED)
        for row in connection.execute(
            f"SELECT id, {', '.join(DERIVED)} FROM products_view ORDER BY id")
    }


def partner_cuts(connection):
    """Each product's partner cut, by the one function that computes it."""
    return {
        row["id"]: psells.partner_share_for(row)
        for row in psells.all_products(connection)
    }


def verify(source, target):
    """Raise MigrationError naming the first thing that differs."""
    for table in TABLES:
        expected = source_rows(source, table)
        stored = target_rows(target, table)
        if stored != expected:
            raise MigrationError(f"{table} does not match the source")

    if derived_quantities(target) != derived_quantities(source):
        raise MigrationError("derived stock quantities do not match")

    if psells.dashboard_totals(target) != psells.dashboard_totals(source):
        raise MigrationError("dashboard figures do not match")

    if partner_cuts(target) != partner_cuts(source):
        raise MigrationError("partner cuts do not match")

    for table in TABLES:
        next_id = target.execute(
            f"SELECT nextval(pg_get_serial_sequence('{table}', 'id')) AS n"
        ).fetchone()["n"]
        highest = target.execute(
            f"SELECT COALESCE(max(id), 0) AS n FROM {table}").fetchone()["n"]
        if next_id <= highest:
            raise MigrationError(f"{table} would reuse an id")


def migrate(source, target):
    """Copy, check, and keep all of it or none of it. Returns the row counts.

    target.transaction() is a real transaction on a connection from
    psells.connect, and a savepoint on a test's connection. Either way, an
    exception inside it undoes every insert.

    The nextval calls in verify use up one id per table, which is harmless:
    sequences never promise consecutive ids, only new ones.
    """
    check_source(source)

    with target.transaction():
        for table in TABLES:
            if target.execute(
                    f"SELECT count(*) AS n FROM {table}").fetchone()["n"]:
                raise MigrationError(
                    f"The database already holds {table}; it must be empty")

        # A row PostgreSQL's schema refuses becomes a sentence rather than a
        # traceback. Raised inside the block, so the rollback still happens.
        try:
            for table in TABLES:
                load(target, table, source_rows(source, table))
        except psycopg.Error as error:
            raise MigrationError(
                f"PostgreSQL refused a row in {table}: "
                f"{error.diag.message_primary}") from error

        verify(source, target)

    return {table: len(source_rows(source, table)) for table in TABLES}


def main(argv):
    if len(argv) != 2:
        print("Usage: python migrate_to_postgres.py /path/to/copy-of-psells.db")
        return 2

    try:
        source = open_source(argv[1])
    except MigrationError as error:
        print(f"Migration refused: {error}. Nothing was written.")
        return 1

    try:
        target = psells.connect()
        try:
            counts = migrate(source, target)
        finally:
            target.close()
    except (MigrationError, psells.DatabaseUnavailable) as error:
        print(f"Migration refused: {error}. Nothing was written.")
        return 1
    finally:
        source.close()

    for table, count in counts.items():
        print(f"{table:<10}{count:>6} rows")
    print("Every row and column, every product's stock and partner cut, and "
          "all nine dashboard figures match the source. Committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
