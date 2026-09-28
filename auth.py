"""Passwords and sessions: who is logged in, and for how long.

One module holds every rule about logging in, so the pages, the API and
set_password.py all ask the same functions and none of them decides for itself.
It knows nothing about HTTP: the cookie and the form are web.py's business.
What it is handed is a connection, a username and password, or the value a
cookie carried, and the time.

The time is always passed in, never read here. The routes pass now(), and the
tests pass a fixed moment, so "two hours later" is a line of arithmetic in a
test rather than a two-hour wait.

Passwords are hashed with Argon2id, deliberately slow and memory hungry, so
that a copy of the users table is expensive to guess against. The parameters
are argon2-cffi's defaults, which follow RFC 9106's recommendation for most
systems; they are written into every hash, so a hash made today still checks
after the defaults change, and is upgraded the next time its password is used.

A session is identified by a long random value that only the browser holds. The
table keeps its SHA-256 digest, so the database, or a backup of it, holds
nothing a browser could present. SHA-256 rather than Argon2 because the value is
random, 256 bits of it: there is nothing to guess, so a slow hash would only
slow every request down.
"""

import datetime
import functools
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


# A session ends after this long without a request, and this long after it
# began whatever happens. Pierre's decision, 27 September 2026.
IDLE_LIMIT = datetime.timedelta(hours=2)
ABSOLUTE_LIMIT = datetime.timedelta(hours=12)

# Pierre's decision, 27 September 2026: 15, as NIST SP 800-63B asks for a
# password that is the only factor, raised from 10 when the login went public
# in Phase 06. Length only: no required digits or symbols, which push people
# to predictable patterns rather than stronger passwords.
MINIMUM_PASSWORD_LENGTH = 15

_hasher = PasswordHasher()


class AccountError(Exception):
    """A username or password that set_password refuses, with the reason."""


def now():
    """The current moment, with its time zone, as the tables store it."""
    return datetime.datetime.now(datetime.timezone.utc)


def digest(value):
    """The SHA-256 digest a session is stored under."""
    return hashlib.sha256(value.encode()).digest()


# Passwords --------------------------------------------------------------------

def password_problem(password):
    """Why a new password is refused, or None if it may be used."""
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        return (f"The password must be at least {MINIMUM_PASSWORD_LENGTH} "
                "characters long.")
    return None


def username_problem(username):
    """Why a username is refused, or None. The table holds the same rule."""
    if not username or username != username.strip():
        return "The username must not be blank or start or end with a space."
    return None


def hash_password(password):
    return _hasher.hash(password)


def verify_password(stored_hash, password):
    """True if password is the one stored_hash was made from.

    argon2-cffi answers a wrong password by raising, and a damaged hash by
    raising something else; both mean "no" here.
    """
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@functools.cache
def _stand_in_hash():
    """A hash to check against when the username does not exist.

    Made the first time it is needed rather than at import, because hashing
    takes a noticeable fraction of a second and most imports never need it.
    """
    return _hasher.hash(secrets.token_urlsafe(32))


def check_login(connection, username, password):
    """The id of the user these credentials belong to, or None.

    An unknown username still costs one Argon2 check, against a stand-in hash,
    so the time a refusal takes does not reveal whether the username exists.

    A hash made with parameters weaker than today's is replaced by a new one,
    now that the password is at hand to make it from.
    """
    user = connection.execute(
        "SELECT id, password_hash FROM users WHERE username = %s",
        (username,),
    ).fetchone()

    if user is None:
        verify_password(_stand_in_hash(), password)
        return None

    if not verify_password(user["password_hash"], password):
        return None

    if _hasher.check_needs_rehash(user["password_hash"]):
        connection.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(password), user["id"]),
        )

    return user["id"]


def set_password(connection, username, password):
    """Create the account, or give it a new password, and end its sessions.

    PSells has one account. If it already exists under another name, this
    refuses rather than creating a second one: a second person is a decision
    to take, not a side effect of a typing mistake.

    Every session of the account ends, so a password changed because the old
    one leaked also shuts out whoever used it.

    Raises AccountError with the reason if the username or the password is
    refused.
    """
    problem = username_problem(username) or password_problem(password)
    if problem:
        raise AccountError(problem)

    password_hash = hash_password(password)

    with connection.transaction():
        others = connection.execute(
            "SELECT username FROM users WHERE username <> %s ORDER BY id",
            (username,),
        ).fetchall()
        if others:
            raise AccountError(
                f"PSells already has the account {others[0]['username']!r}. "
                "Give that username to change its password.")

        user_id = connection.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) "
            "ON CONFLICT (username) DO UPDATE "
            "SET password_hash = EXCLUDED.password_hash "
            "RETURNING id",
            (username, password_hash),
        ).fetchone()["id"]

        connection.execute("DELETE FROM sessions WHERE user_id = %s",
                           (user_id,))

    return user_id


# Sessions ---------------------------------------------------------------------

def start_session(connection, user_id, at):
    """Begin a session, and hand back (cookie value, form token).

    The cookie value is returned once, here, and never stored. Sessions that
    have already expired are cleared out at the same time, so the table does
    not grow with every login that was never logged out of.
    """
    cookie_value = secrets.token_urlsafe(32)
    form_token = secrets.token_urlsafe(32)

    with connection.transaction():
        connection.execute(
            "DELETE FROM sessions "
            "WHERE last_seen_at <= %s OR created_at <= %s",
            (at - IDLE_LIMIT, at - ABSOLUTE_LIMIT),
        )
        connection.execute(
            "INSERT INTO sessions (token_digest, user_id, form_token, "
            "created_at, last_seen_at) VALUES (%s, %s, %s, %s, %s)",
            (digest(cookie_value), user_id, form_token, at, at),
        )

    return cookie_value, form_token


def find_session(connection, cookie_value, at):
    """The live session this cookie belongs to, as a dict, or None.

    The dict holds user_id and form_token. Finding a session counts as using
    it, so its idle time starts again from at.

    Whether it has expired is decided in the same statement that marks it
    used, so two requests at once cannot both find a session that only one of
    them should. GREATEST keeps last_seen_at from moving backwards if a clock
    does. An expired session is left for start_session to clear out.
    """
    if not cookie_value:
        return None

    return connection.execute(
        "UPDATE sessions SET last_seen_at = GREATEST(last_seen_at, %s) "
        "WHERE token_digest = %s AND last_seen_at > %s AND created_at > %s "
        "RETURNING user_id, form_token",
        (at, digest(cookie_value), at - IDLE_LIMIT, at - ABSOLUTE_LIMIT),
    ).fetchone()


def end_session(connection, cookie_value):
    """Log out: the session this cookie belongs to stops existing."""
    if cookie_value:
        connection.execute("DELETE FROM sessions WHERE token_digest = %s",
                           (digest(cookie_value),))


def form_token_matches(session, submitted):
    """True if a form sent back the token its session was given.

    compare_digest takes as long whatever the two values are, so how quickly a
    wrong token is refused says nothing about how much of it was right.
    """
    if session is None or not submitted:
        return False
    return secrets.compare_digest(session["form_token"].encode(),
                                  submitted.encode())
