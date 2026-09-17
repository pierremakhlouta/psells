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


@pytest.fixture
def partner_rate(monkeypatch):
    """Pin the default partner share at 40 percent for one test.

    Two reasons, and the second matters more than the first.

    A default-mode product sends partner_share_for to the config file, which is
    read relative to the working directory. data/ is gitignored, so a checkout
    has no config file and the test dies with FileNotFoundError raised four
    frames below the line under test. It passes on a developer's machine and
    fails on CI, which is the worst shape a test failure can take.

    And the real rate is a business figure that does not belong in a public
    repository. Pinning an invented 40 percent keeps it out, and makes every
    expected partner cut in a test arithmetic a reader can check by eye.
    """
    monkeypatch.setattr(psells, "default_partner_share_percent", lambda: 40.0)

    return 40.0
