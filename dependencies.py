"""What a route needs before it can run, shared by every route.

The API in api.py and the pages in web.py each need a database connection for
the length of one request. It lives here rather than in either of them so that
neither has to import the other. api.py includes the page routes, so if web.py
also imported api.py to get its connection, each file would need the other to
have finished loading first, and which one won would depend on which was
imported first. A third module both can import has no such order.
"""

from typing import Annotated

import psycopg
from fastapi import Depends

import psells


def get_connection():
    """One connection per request, closed when the request finishes.

    A connection is not shared between requests. Every route that asks for one
    is a plain def, which FastAPI runs in a thread pool, so two requests can be
    in flight at once, and one connection carries one conversation with the
    server at a time: a shared one would make the second request wait for the
    first, or interleave their transactions.

    psells.connect is used rather than psycopg.connect directly, so autocommit
    and the row factory are set exactly once, in one place.
    """
    connection = psells.connect()

    try:
        yield connection
    finally:
        connection.close()


Connection = Annotated[psycopg.Connection, Depends(get_connection)]
