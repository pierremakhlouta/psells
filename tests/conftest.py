"""Fixtures shared by every test file in this folder.

pytest loads this file on its own and injects what it finds here, so a test
that wants the database only has to name `db` as a parameter. There is nothing
to import and nothing to remember.
"""

import os
import sqlite3

import pytest

import psells


@pytest.fixture
def db():
    """An empty database built from the real schema, held in memory.

    It reads schema.sql itself rather than a copy, so a constraint added there
    is exercised here automatically. Nothing touches the disk and no data files
    are needed, which keeps the suite runnable on a fresh clone and on CI.
    """
    schema_path = os.path.join(os.path.dirname(psells.__file__), "schema.sql")

    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")

    with open(schema_path) as schema:
        connection.executescript(schema.read())

    connection.row_factory = sqlite3.Row

    return connection
