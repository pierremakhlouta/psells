"""Fixtures shared by every test file in this folder.

pytest loads this file on its own and injects what it finds here, so a test
that wants the database only has to name `db` as a parameter. There is nothing
to import and nothing to remember.
"""

import os
import sqlite3

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

import api
import dependencies
import psells
from helpers import TEST_DATABASE_URL


# PostgreSQL -----------------------------------------------------------------

START_TEST_DATABASE = "docker compose --profile test up -d --wait db-test"


@pytest.fixture(scope="session", autouse=True)
def postgres_schema():
    """Build the PostgreSQL schema once, before the first test runs.

    Autouse and session scoped, so every run needs the test database, and a
    run without it stops at once with one sentence saying how to start it. A
    database test skipped for want of a server would look like a pass.

    It wipes everything in the database it is pointed at, so it refuses any
    database whose name does not end in _test. The real database is not
    reachable from outside its stack anyway; this makes pointing the suite at
    it by mistake a refusal rather than a loss.
    """
    name = conninfo_to_dict(TEST_DATABASE_URL).get("dbname", "")
    if not name.endswith("_test"):
        pytest.exit(
            f"Refusing to run the tests against the database {name!r}: they "
            "wipe it, so its name must end in _test.",
            returncode=pytest.ExitCode.USAGE_ERROR,
        )

    schema_path = os.path.join(
        os.path.dirname(psells.__file__), "schema_postgres.sql")

    try:
        connection = psycopg.connect(
            TEST_DATABASE_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.exit(
            "No test database at 127.0.0.1:5433 (or PSELLS_TEST_DATABASE_URL). "
            "Start it with: " + START_TEST_DATABASE,
            returncode=pytest.ExitCode.USAGE_ERROR,
        )

    with connection:
        connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        connection.execute("CREATE SCHEMA public")
        with open(schema_path) as schema:
            connection.execute(schema.read())


@pytest.fixture
def pg():
    """A PostgreSQL connection whose every change is undone after the test.

    The test runs inside one transaction that is rolled back at the end, so
    tests never see each other's rows and nothing has to be deleted. A
    statement the database refuses aborts the transaction it is in, so a test
    that expects a refusal wraps the statement in pg.transaction(), which
    inside an open transaction is a savepoint: the refusal rolls back to it and
    the test carries on.

    Rows come back as dicts, so row["name"] reads a column by name.

    Sequences are the one thing a rollback does not undo. Ids a test used are
    gone for good, which is exactly the behaviour that ends id reuse.
    """
    connection = psycopg.connect(TEST_DATABASE_URL, row_factory=dict_row)

    # Opens the transaction now, so that a pg.transaction() block in the test
    # becomes a savepoint inside it rather than a transaction of its own that
    # would commit.
    connection.execute("SELECT 1")

    yield connection

    connection.rollback()
    connection.close()


# SQLite ---------------------------------------------------------------------

@pytest.fixture
def db():
    """An empty database built from the real schema, held in memory.

    It reads schema.sql itself rather than a copy, so a constraint added there
    is exercised here automatically. Nothing touches the disk and no data files
    are needed, which keeps the suite runnable on a fresh clone and on CI.
    """
    schema_path = os.path.join(os.path.dirname(psells.__file__), "schema.sql")

    # check_same_thread is off for the same reason the API turns it off: the
    # API tests drive endpoints through a thread pool, and this one connection
    # is then touched from a thread other than the one that made it. Every test
    # here is single threaded and uses the connection one call at a time, so
    # nothing is shared concurrently.
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.execute("PRAGMA foreign_keys = ON")

    with open(schema_path) as schema:
        connection.executescript(schema.read())

    connection.row_factory = sqlite3.Row

    yield connection

    # Closed rather than left to the garbage collector. From Python 3.13 an
    # unclosed sqlite3 connection raises ResourceWarning when it is collected,
    # and with warnings as errors that fails whichever test happens to be
    # running at the time, not the one that leaked.
    connection.close()


@pytest.fixture
def partner_rate(monkeypatch):
    """Pin the default partner share at 40 percent for one test.

    Two reasons, and the second matters more than the first.

    A default-mode product sends partner_share_for to the config file. data/ is
    gitignored, so a checkout has no config file at all and the test dies with
    FileNotFoundError raised four frames below the line under test. It passes on
    a developer's machine and fails on CI, which is the worst shape a test
    failure can take. Resolving that path beside psells.py rather than beside
    the shell removed one cause of this and not this one: on CI the file is
    missing, not merely somewhere else.

    And the real rate is a business figure that does not belong in a public
    repository. Pinning an invented 40 percent keeps it out, and makes every
    expected partner cut in a test arithmetic a reader can check by eye.
    """
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 40.0)

    return 40.0


@pytest.fixture
def answers(monkeypatch):
    """Queue the replies a feature function will read from input().

    Call it with one string per question, in the order the function asks. Each
    call to input() takes the next one, and running out raises StopIteration,
    so a function that asks more questions than the test expected fails loudly
    instead of hanging.

    Remember that a rejected answer costs two: every ask_ helper loops until
    what it gets is valid, so feeding "abc" to ask_int consumes an answer and
    asks again.
    """
    def queue(*values):
        remaining = iter(values)
        monkeypatch.setattr("builtins.input", lambda prompt="": next(remaining))

    return queue


@pytest.fixture
def client(db, partner_rate):
    """A test client whose requests run against the in-memory database.

    It calls the application directly rather than opening a socket, and swaps
    the connection dependency for the in-memory db fixture, so no request made
    through it touches a file. Here rather than in test_api.py so that any test
    file driving the application gets the same override.

    The override is keyed on dependencies.get_connection, the function itself,
    so it replaces the connection for every route that asks for one.
    """
    api.app.dependency_overrides[dependencies.get_connection] = lambda: db

    yield TestClient(api.app)

    api.app.dependency_overrides.clear()
