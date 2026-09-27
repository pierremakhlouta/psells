"""What a route needs before it can run, shared by every route.

The API in api.py and the pages in web.py each need a database connection for
the length of one request, and every route but the login page needs a live
session. Both live here rather than in either of them so that neither has to
import the other. api.py includes the page routes, so if web.py
also imported api.py to get its connection, each file would need the other to
have finished loading first, and which one won would depend on which was
imported first. A third module both can import has no such order.
"""

from typing import Annotated

import psycopg
from fastapi import Depends, HTTPException, Request

import auth
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


# Who is asking -----------------------------------------------------------------
#
# Every route but the login page needs a live session, and gets it from one of
# the two functions below, set on its router rather than on each route, so a
# route added to a router cannot be added without it. tests/test_login.py
# calls every route the application has without a session and fails on any
# that answers.
#
# Both depend on Connection, and FastAPI makes one connection per request
# however many dependencies ask for it, so the session is read and the route
# runs on the same connection.

# __Host- makes the browser refuse the cookie unless it is Secure, set by this
# host itself with no Domain, and for Path=/, so no other name, not even a
# subdomain, can set or overwrite it.
SESSION_COOKIE = "__Host-psells_session"


class LoginRequired(Exception):
    """A page was asked for without a live session. api.py answers it with a
    redirect to the login page."""


def current_session(request: Request, connection: Connection):
    """The live session the request's cookie belongs to, or None.

    Kept on request.state as well, so a page can reach its form token without
    every route passing it along.
    """
    session = auth.find_session(
        connection, request.cookies.get(SESSION_COOKIE), auth.now())
    request.state.session = session
    return session


Session = Annotated[dict | None, Depends(current_session)]


def require_page_session(session: Session):
    """For pages: without a session, send the browser to the login page."""
    if session is None:
        raise LoginRequired()
    return session


def require_api_session(session: Session):
    """For the API: without a session, 401 and a sentence, as JSON."""
    if session is None:
        raise HTTPException(status_code=401, detail="Log in first.")
    return session
