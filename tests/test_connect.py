"""Tests for psells.connect, the one place the application opens a database.

Every other test runs on the fixture's connection, inside a transaction that
is rolled back, where the application's own write blocks are savepoints. That
is what keeps the tests apart, and it means none of them can show that a write
made through psells.connect is ever committed. These can, so they commit for
real, into the test database, and delete what they wrote afterwards.
"""

import psycopg
import pytest

import psells

from helpers import TEST_DATABASE_URL


@pytest.fixture
def real_connection(monkeypatch):
    """A connection from psells.connect, pointed at the test database.

    Rows it commits are deleted at the end, because the next test's fixture
    expects empty tables and moves the sequences as if nothing else existed.
    """
    monkeypatch.setattr(psells, "DATABASE_URL", TEST_DATABASE_URL)
    connection = psells.connect()

    yield connection

    connection.close()
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as cleanup:
        cleanup.execute("DELETE FROM payments WHERE notes = 'test_connect'")


def committed_payments():
    """What a separate connection sees, which is only what was committed."""
    with psycopg.connect(TEST_DATABASE_URL) as other:
        return other.execute(
            "SELECT COUNT(*) FROM payments WHERE notes = 'test_connect'"
        ).fetchone()[0]


def test_a_write_through_psells_connect_is_committed(real_connection):
    # With autocommit off, the first read would open a transaction and the
    # write below would be a savepoint inside it, visible here and lost when
    # the connection closed. A second connection sees only what committed.
    psells.all_payments(real_connection)

    psells.create_payment(real_connection, 100, "2026-06-05", "test_connect")

    assert committed_payments() == 1


def test_rows_read_by_column_name(real_connection):
    psells.create_payment(real_connection, 100, "2026-06-05", "test_connect")

    payment = psells.all_payments(real_connection)[-1]

    assert payment["notes"] == "test_connect"


def test_no_database_setting_is_a_sentence(monkeypatch):
    monkeypatch.setattr(psells, "DATABASE_URL", "")

    with pytest.raises(psells.DatabaseUnavailable) as refused:
        psells.connect()

    assert "PSELLS_DATABASE_URL is not set" in str(refused.value)
    assert "docker compose exec app python psells.py" in str(refused.value)


def test_a_database_that_does_not_answer_is_a_sentence(monkeypatch):
    # Nothing listens on port 1. connect_timeout keeps the refusal quick.
    monkeypatch.setattr(
        psells, "DATABASE_URL",
        "postgresql://nobody:nothing@127.0.0.1:1/none?connect_timeout=2")

    with pytest.raises(psells.DatabaseUnavailable) as refused:
        psells.connect()

    assert str(refused.value).startswith("Could not reach the database")


def test_the_terminal_app_stops_with_the_sentence(monkeypatch, capsys,
                                                  partner_rate):
    monkeypatch.setattr(psells, "DATABASE_URL", "")

    with pytest.raises(SystemExit) as stopped:
        psells.main()

    assert stopped.value.code == 1
    assert "Database error: PSELLS_DATABASE_URL is not set" in (
        capsys.readouterr().out)
