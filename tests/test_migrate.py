"""Tests for migrate_to_postgres.py, the one-time move out of SQLite.

The source is a real SQLite file built from the schema PSells used before
PostgreSQL, filled with invented rows chosen to catch the mistakes a copy can
make: ids with gaps, all three partner-share modes, a product discontinued at
retail, a percentage whose float needs every digit, and history on some
products and not others. The target is the test's own connection, so the
migration's transaction is a savepoint and everything it writes is undone.
"""

import os
import sqlite3
from datetime import date

import pytest

import migrate_to_postgres as migration
import psells

from helpers import add_product


SQLITE_SCHEMA = os.path.join(os.path.dirname(__file__), "sqlite_schema.sql")


def build_source(path, extra_sql=""):
    """A SQLite file in the old shape, holding the invented rows below.

    extra_sql runs last, with foreign keys switched off, the way every SQLite
    connection started unless it asked otherwise: that is how a row pointing
    at nothing could ever have been stored.
    """
    connection = sqlite3.connect(path)
    try:
        _fill(connection, extra_sql)
    finally:
        connection.close()


def _fill(connection, extra_sql):
    with open(SQLITE_SCHEMA) as schema:
        connection.executescript(schema.read())
    connection.executescript("""
        INSERT INTO products VALUES
            (1, 'Watches', 'Field Watch', 3, 20000, 14000, 0, 'default',
             NULL, NULL, 'Brand New', ''),
            (2, 'Watches', 'Trail Watch', 2, 30000, 22000, 0, 'custom_percent',
             33.333333333333336, NULL, 'Used', 'no box'),
            (5, 'Hats', 'Field Cap', 5, 4500, 3000, 0, 'custom_amount',
             NULL, 1200, 'Brand New', ''),
            (9, 'Watches', 'Dive Watch', 1, 0, 18000, 1, 'custom_amount',
             NULL, 9000, 'Used', 'scratched bezel');
        INSERT INTO sales VALUES
            (1, '2026-05-14', 1, 1, 15000, 8000),
            (4, '2026-06-02', 2, 2, 21000, 10000),
            (7, '2026-07-19', 5, 1, 2800, 1200);
        INSERT INTO returns VALUES (3, '2026-06-30', 5, 2, 'sent back');
        INSERT INTO payments VALUES
            (1, '2026-06-05', 15000, 'Cash'),
            (6, '2026-07-25', 4000, '');
    """)
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.executescript(extra_sql)
    connection.commit()


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "psells.db"
    build_source(path)
    connection = migration.open_source(str(path))
    yield connection
    connection.close()


def counts(db):
    return {table: db.execute(f"SELECT count(*) AS n FROM {table}")
            .fetchone()["n"] for table in migration.TABLES}


def test_every_row_arrives_with_its_own_id_and_values(db, source,
                                                      partner_rate):
    moved = migration.migrate(source, db)

    assert moved == {"products": 4, "sales": 3, "returns": 1, "payments": 2}
    assert [row["id"] for row in db.execute(
        "SELECT id FROM products ORDER BY id")] == [1, 2, 5, 9]
    trail = db.execute("SELECT * FROM products WHERE id = 2").fetchone()
    assert trail["partner_share_percent"] == 33.333333333333336
    assert trail["notes"] == "no box"
    sale = db.execute("SELECT * FROM sales WHERE id = 4").fetchone()
    assert (sale["date"], sale["item_id"], sale["partner_share_cents"]) == (
        date(2026, 6, 2), 2, 10000)


def test_the_figures_after_the_move_are_the_figures_before_it(db, source,
                                                              partner_rate):
    before = psells.dashboard_totals(source)

    migration.migrate(source, db)

    assert psells.dashboard_totals(db) == before
    assert db.execute("SELECT quantity_available FROM products_view "
                      "WHERE id = 5").fetchone()["quantity_available"] == 2


def test_the_next_record_gets_a_new_id_in_every_table(db, source,
                                                      partner_rate):
    migration.migrate(source, db)

    product_id = psells.create_product(
        db, "Hats", "New Cap", 1, False, 1000, 900, "New", "",
        "custom_amount", None, 100)
    payment_id = psells.create_payment(db, 100, "2026-08-01", "")

    assert product_id > 9
    assert payment_id > 6


def test_a_database_that_already_holds_records_is_refused(db, source,
                                                          partner_rate):
    add_product(db, 1, quantity_received=1)

    with pytest.raises(migration.MigrationError, match="must be empty"):
        migration.migrate(source, db)

    assert counts(db) == {"products": 1, "sales": 0, "returns": 0,
                          "payments": 0}


def test_any_difference_undoes_everything(db, source, partner_rate,
                                          monkeypatch):
    # Corrupt what is loaded, not what is compared against: the check must
    # catch it, and the rollback must leave nothing behind.
    original = migration.load

    def load_with_a_wrong_price(target, table, rows):
        if table == "sales":
            rows = [dict(rows[0], sale_price_cents=rows[0]["sale_price_cents"]
                         + 1)] + rows[1:]
        original(target, table, rows)

    monkeypatch.setattr(migration, "load", load_with_a_wrong_price)

    with pytest.raises(migration.MigrationError, match="sales"):
        migration.migrate(source, db)

    assert counts(db) == {"products": 0, "sales": 0, "returns": 0,
                          "payments": 0}


@pytest.mark.parametrize("check, sentence", [
    ("derived_quantities", "derived stock"),
    ("partner_cuts", "partner cuts"),
    ("dashboard_totals", "dashboard"),
])
def test_each_check_after_the_rows_refuses_on_its_own(db, source,
                                                      partner_rate,
                                                      monkeypatch, check,
                                                      sentence):
    """The rows are compared first, so while they match these three can never
    disagree, which means no ordinary run has ever seen one refuse. Here the
    PostgreSQL side of one check is made to answer differently, and that
    check alone must stop the migration."""
    owner = psells if check == "dashboard_totals" else migration
    original = getattr(owner, check)

    def differs_on_postgres(connection):
        answer = original(connection)
        if isinstance(connection, sqlite3.Connection):
            return answer
        return {"a different": "answer"}

    monkeypatch.setattr(owner, check, differs_on_postgres)

    with pytest.raises(migration.MigrationError, match=sentence):
        migration.migrate(source, db)

    assert counts(db)["products"] == 0


def test_a_sequence_left_behind_its_ids_is_refused(db, source, partner_rate,
                                                  monkeypatch):
    """load moves each sequence past its highest id, so while it does, the
    check for a reused id can never fire. Here the sequence is put back to 1
    after loading, and that check alone must stop the migration."""
    original = migration.load

    def load_then_rewind(target, table, rows):
        original(target, table, rows)
        target.execute("SELECT setval(pg_get_serial_sequence(%s, 'id'), 1, "
                       "false)", (table,))

    monkeypatch.setattr(migration, "load", load_then_rewind)

    with pytest.raises(migration.MigrationError, match="would reuse an id"):
        migration.migrate(source, db)


def test_a_row_postgresql_refuses_is_a_sentence_and_undoes_everything(
        db, source, partner_rate, monkeypatch):
    original = migration.source_rows

    def a_product_with_nothing_received(connection, table):
        rows = original(connection, table)
        if table == "products":
            rows[-1] = dict(rows[-1], quantity_received=0)
        return rows

    monkeypatch.setattr(migration, "source_rows",
                        a_product_with_nothing_received)

    with pytest.raises(migration.MigrationError,
                       match="PostgreSQL refused a row in products"):
        migration.migrate(source, db)

    assert counts(db)["products"] == 0


def test_a_source_with_an_orphaned_sale_is_refused(db, tmp_path,
                                                   partner_rate):
    path = tmp_path / "orphan.db"
    build_source(path, "INSERT INTO sales VALUES "
                       "(8, '2026-08-01', 99, 1, 100, 10);")
    source = migration.open_source(str(path))

    with pytest.raises(migration.MigrationError, match="does not exist"):
        migration.migrate(source, db)

    source.close()
    assert counts(db)["products"] == 0


def test_the_source_is_opened_read_only(source):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        source.execute("DELETE FROM payments")


def test_a_missing_source_file_is_a_sentence_not_an_empty_database(tmp_path):
    missing = tmp_path / "nothing-here.db"

    with pytest.raises(migration.MigrationError, match="No SQLite file"):
        migration.open_source(str(missing))

    assert not missing.exists()


def test_the_command_line_says_nothing_was_written(tmp_path, capsys):
    code = migration.main(["migrate_to_postgres.py",
                           str(tmp_path / "nothing-here.db")])

    assert code == 1
    assert "Nothing was written." in capsys.readouterr().out
