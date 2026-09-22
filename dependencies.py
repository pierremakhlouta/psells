"""What a route needs before it can run, shared by every route.

The API in api.py and the pages in web.py each need a database connection for
the length of one request. It lives here rather than in either of them so that
neither has to import the other. api.py includes the page routes, so if web.py
also imported api.py to get its connection, each file would need the other to
have finished loading first, and which one won would depend on which was
imported first. A third module both can import has no such order.
"""

import sqlite3
from typing import Annotated

from fastapi import Depends

import psells


def get_connection():
    """One connection per request, closed when the request finishes.

    A connection cannot be shared between requests. Python's sqlite3 refuses
    to use a connection from any thread other than the one that opened it, and
    every route that asks for one is a plain def, which FastAPI runs in a thread
    pool. A module-level connection would work in testing and fail under a
    second caller.

    psells.connect is used rather than sqlite3.connect directly, so the foreign
    key pragma and the row factory are applied exactly once, in one place.
    """
    connection = psells.connect(check_same_thread=False)

    try:
        yield connection
    finally:
        connection.close()


Connection = Annotated[sqlite3.Connection, Depends(get_connection)]
